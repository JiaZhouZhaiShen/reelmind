# REELMIND Web 架构铁律与执行手册

> ⚠️ AI 执行铁律：先思考，再出方案，方案经验证后确认，确认后备份再修改，修改后验证，验证完删备份。

> 涵盖后端 FastAPI、前端 React SPA、双数据库、管道调度。每条附带执行检查方案，可融入 Code Review 和 CI。

---

## 一、后端架构铁律

---

### ① Server 只转发不做计算

**规则：** Web 容器不加载 AI 模型、不执行 GPU 推理。所有 AI 请求通过 HTTP proxy 转发到 AI 容器。

```python
# ✅ 正确
@router.post("/process")
async def trigger_ai_pipeline(req: AITriggerRequest):
    result = await _ai_post("/pipeline/start", {...})
    return {"status": "queued", "task_id": result.get("task_id")}

# ❌ 禁止：在 server 里直接调模型推理
```

**🔍 执行检查：**
```
grep -rn "torch\|transformers\|model\.predict\|model\.encode" server/app/api/ --include="*.py"
# 如果返回空，则合规
```

**原因：** AI 跑满 GPU 时 Web API 不因此变慢。Web 容器内存 2G，AI 容器 14G，资源隔离。

---

### ② Router 文件不超过 500 行，以职责单一优先

**规则：** 每个 `api/*.py` 不超过 500 行。同一文件处理多个无关职责比行数超限更应优先拆分。

```python
# 好信号：一个文件同时处理了 pipeline 触发 + 结果查询 + SSE 管理 → 必须拆
```

**🔍 执行检查：**
```bash
# 检查行数超限的 api 文件
find server/app/api -name "*.py" -exec wc -l {} \; | sort -rn | awk '$1 > 500'
# 检查职责混杂——搜索一个文件中 import 了多个无关模块
grep -l "from.*models.*import\|from.*services\|from.*core" server/app/api/ai/*.py
```

**历史：** `api/ai.py` 3200 行已拆分 → `ai_proxy.py` / `ai_pipeline.py` / `ai_results.py`。

**当前违规文件需关注：** `api/assets.py` (1104 行)、`core/indexer.py` (1217 行)、`ai_service/pipeline.py` (897 行)。

---

### ③ 后端不做渲染计算

**规则：** 后端不做渲染计算，但业务聚合和状态推导可以放后端。
- **放前端的信号：** 只是把数字转百分比、算进度条
- **放后端的信号：** 解析逻辑需要知道后端内部协议细节（如 step 字符串格式）

```python
# ✅ 后端只返回原始数据
{"engines": {"scene": "completed", "yolo": "running"}, "step": "YOLO [5/10]"}

# ❌ 后端写了 40 行进度推算
def _compute_model_progress(step, progress, total) -> dict:
    ...
```

**🔍 执行检查：**
```bash
# 搜索后端可能在内联做前端渲染逻辑的函数
grep -n "def _compute\|def _format\|def _render\|def _display" server/app/api/ --include="*.py"
```

---

### ④ 双数据库各司其职，不混用

| 数据 | 存哪里 | 谁写 | 谁读 |
|------|--------|------|------|
| Asset 元数据、管道状态 | PG | Server + Orchestrator + AI Worker | Server |
| AI 推理结果（场景/字幕/标签） | SQLite | AI Worker | Server |
| CLIP 向量索引 | PG (pgvector) | AI Worker | Server |

**规则：** 不存在一条数据同时写两个库的场景。如果发现双写，说明设计有问题。

**🔍 执行检查：**
```bash
# 搜索后端同时操作 PG + SQLite 的代码
grep -n "get_ai_session\|get_pg_session\|async_session_factory\|sync_session_factory" server/app/api/*.py
# 从同一函数中同时调用了 PG 和 SQLite 会话 → 可能违反
```

---

## 二、前端架构铁律

---

### ⑤ 所有业务状态归 Zustand store，组件不存

**规则：** API 返回的数据必须进 store。组件 `useState` 只允许存 UI 状态（输入框值、下拉展开、选中项）。

```tsx
// ✅ 正确
const pendingCounts = useAIStore(s => s.pendingCounts)

// ❌ 禁止
const [pendingCounts, setPendingCounts] = useState(null)
useEffect(() => { api.xxx().then(setPendingCounts) }, [])
```

**🔍 执行检查：**
```bash
# 搜索组件中用 useState + useEffect 调 API 的模式
grep -n "useState\|useEffect\|fetch\|await.*api\." web/src/pages/*.tsx web/src/components/**/*.tsx | grep -B1 "useState\|useEffect"
# 重点关注那些 useState + useEffect + api.xxx 连续三行出现的文件
```

---

### ⑥ 子组件不从父组件接收业务 props

**规则：** 子组件优先从 store 读数据。父组件不向下传递业务 props，除非需要单元测试或跨项目复用——此时允许 props override。

```
优先顺序：默认从 store 读 → 测试或复用时 props override
```

```tsx
// ✅ 正确
<ProcessingQueue />   // 内部自己 useAIStore(s => s.queueStatus)

// ❌ 禁止：props 穿透超过 5 个业务 props
```

**🔍 执行检查（Code Review checklist）：**
1. 看 JSX 中传了多少 props → 超过 5 个业务 props 即警告
2. 检查子组件第一行是否用了 `useXxxStore` → 没有即违反
3. `grep -n "\.\.\.props\|\w+=\{" web/src/components/ai/*.tsx` 看 props 透传

---

### ⑦ 每个子组件自包含 loading/error/empty 状态

**规则：** 每个组件内部处理这三种状态，不依赖父组件。这也是空 catch 不会引发白屏的根本保障。

```tsx
export function GPUInfo() {
  const gpuInfo = useAIStore(s => s.gpuInfo)
  const loading = useAIStore(s => s.gpuInfoLoading)

  if (loading) return <SkeletonCard />
  if (!gpuInfo.total) return <div className="text-gray-500">无 GPU 信息</div>
  return <div>...</div>
}
```

**🔍 执行检查：**
```bash
# 搜索没有 loading/empty 处理的组件
grep -L "loading\|Loading\|Skeleton\|!.*\b\(data\|items\|list\|info\|status\)\b" web/src/components/**/*.tsx
```

---

### ⑧ 整页必须被 Error Boundary 包裹

**规则：** 每个路由页面外层包 Error Boundary。

```tsx
<Route path="/ai" element={
  <ErrorBoundary fallback={<AIPageError />}>
    <AIEnginePage />
  </ErrorBoundary>
} />
```

**🔍 执行检查：**
```bash
# 检查 App.tsx 中哪些 Route 没有 ErrorBoundary 包裹
grep -n "<Route\|<ErrorBoundary" web/src/App.tsx
# 手动比对：Route 数量 vs ErrorBoundary 数量
```

---

### ⑨ 高频组件加 React.memo 保护（新增）

**规则：** 列表项、卡片、侧边栏等高频重渲染组件用 `React.memo` 包裹。**全项目零 React.memo 是性能 bug。**

**优先级：** `VideoCard` → `SearchVideoCard` → `Sidebar` → `AIPendingOverview` → `GPUInfo` → `AIModelStatus`

```tsx
// ✅ 正确
export const VideoCard = React.memo(function VideoCard({ asset }: Props) {
  return <div>...</div>
})
```

**🔍 执行检查（lint 规则）：**
```bash
# 找可能的列表项组件——文件名含 Card/Item/Row 且无 memo
grep -L "React.memo\|memo(" web/src/components/*Card*.tsx web/src/components/*Item*.tsx
```

---

### ⑩ Store 按 domain 拆分，禁止上帝 store（新增）

**规则：** 每个 Zustand store 只管理一个业务域。`app.ts` 当前 460 行涵盖 auth/libraries/assets/search/grid/batch/admin 等多个域，必须拆分。

```
推荐拆分方案：
├── stores/
│   ├── auth.ts       # 登录/用户
│   ├── asset.ts      # 资产列表/搜索
│   ├── ai.ts         # AI 引擎（已有）
│   ├── admin.ts      # 管理后台
│   └── app.ts        # 仅保留 UI 全局状态（sidebar、theme）
```

**🔍 执行检查：**
```bash
# 检查单个 store 文件行数
wc -l web/src/stores/*.ts
# app.ts > 300 行即需拆分
```

---

### ⑪ 清理死代码和重构残留（新增）

**规则：** 不允许 `.bak`、`.refactor-backup`、`.original` 文件存在。不使用的页面组件必须在同一 PR 中删除。

```bash
# ❌ 以下文件必须删除
web/src/pages/AssetDetail.tsx               # V2 已替代，零引用
web/src/api/*.refactor-backup               # 重构残留 (8 个)
web/src/api/*.bak                           # 备份残留
web/src/stores/*.bak
web/src/components/ai/*.bak
```

**🔍 执行检查：**
```bash
# 在 CI 中运行
find web/src -name "*.bak" -o -name "*.bak2" -o -name "*.refactor-backup" -o -name "*.original"
# 有输出即违规
```

---

### ⑫ TypeScript 严格检查（新增）

**规则：** 必须开启 `noUnusedLocals` 和 `noUnusedParameters`。这两个选项关闭意味着代码腐化入口大开。

```json
// tsconfig.json
{
  "compilerOptions": {
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  }
}
```

**🔍 执行检查：**
```bash
# 在 package.json 中增加
"scripts": {
  "typecheck": "tsc --noEmit",
}
# CI 步骤
pnpm typecheck
```

---

### ⑬ i18n 禁止硬编码中文字符串（新增）

**规则：** 所有用户可见的文本必须走 `t('key')`，禁止直接在组件/js 中写中文。

```tsx
// ✅ 正确
<ErrorBar message={t('errors.loadFailed')} />

// ❌ 禁止
<ErrorBar message="无法加载库列表" />
```

**当前违规位置（待修）：**
- `stores/app.ts`：`"无法加载库列表:"`、`"搜索失败"`、`"删除失败"`
- `VideoPlayer.tsx`：`"运行正常"`、`"负载偏高"`、`"高负载"`、`"加载中..."`

**🔍 执行检查：**
```bash
# 搜索中文引号（匹配中文字符的字符串）
grep -rn '["\x27].*[一-鿿].*["\x27]' web/src/ --include="*.tsx" --include="*.ts" | grep -v "i18n\|locales\|zh.json\|en.json\|node_modules"
```

---

### ⑭ 构建配置：分包 + 按环境控制 sourcemap（新增）

**规则：** Vite 构建必须配置 `manualChunks` 分包，`sourcemap` 仅开发环境开启。

```ts
// vite.config.ts
build: {
  sourcemap: process.env.NODE_ENV !== 'production',
  rollupOptions: {
    output: {
      manualChunks: {
        vendor: ['react', 'react-dom', 'react-router-dom'],
        state: ['zustand'],
        i18n: ['i18next', 'react-i18next'],
      }
    }
  }
}
```

**🔍 执行检查：**
```bash
# 检查构建产物
ls -la web/dist/assets/
# 应该有 vendor-xxx.js、state-xxx.js、i18n-xxx.js 等多个 chunk
# 如果只有一个 index-xxx.js → 未分包
```

---

### ⑮ 页面组件不超过 500 行（新增）

**规则：** 每个页面组件不超过 500 行。超过即拆分子组件。

```bash
# 当前违规（待拆分）
pages/AssetGrid.tsx        # 1032 行 → 拆 FilterBar / AssetList / GroupView
components/VideoPlayer.tsx # 763 行 → 拆 Controls / Shortcuts / SubtitlePanel
```

**🔍 执行检查：**
```bash
find web/src/pages -name "*.tsx" -exec wc -l {} \; | sort -rn | awk '$1 > 500'
find web/src/components -name "*.tsx" -exec wc -l {} \; | sort -rn | awk '$1 > 500'
```

---

## 三、API 层铁律

---

### ⑯ API 按域拆分文件

**规则：** `api/` 目录按业务域拆分：

```
api/
├── base.ts      # request() + token 管理
├── auth.ts      # 登录/注册
├── assets.ts    # 资产
├── ai.ts        # AI 引擎
├── system.ts    # 系统设置
├── tags.ts      # 标签
└── logs.ts      # 日志
```

`client.ts` 只做 barrel 导出，不包含业务代码。

**🔍 执行检查：**
```bash
# client.ts 不能超过 50 行
wc -l web/src/api/client.ts
# 新 API 必须建新文件，不能在 client.ts 里加方法
```

---

### ⑰ 所有 API 调用的 catch() 必须给出用户可见反馈

**规则：** 禁止空 `catch(() => {})`。

```tsx
// ✅ 正确
try { const data = await api.getPendingAssetCount() }
catch (err) { setError("连接服务器失败，请检查服务状态") }

// ❌ 禁止
try { const data = await api.getPendingAssetCount() }
catch {}
```

**例外（允许空 catch）：** `video.play().catch(() => {})` — 浏览器 autoplay 策略、clipboard API、SSE JSON 解析异常。

**🔍 执行检查：**
```bash
# 搜索空 catch（排除允许的例外）
grep -rn "catch\s*\(\)\s*=>\s*{}\|catch\s*{}" web/src/ --include="*.tsx" --include="*.ts" | grep -v "video\.play\|clipboard\|node_modules"
```

---

### ⑱ 统一错误类型和错误展示位置

**规则：** 使用 `GlobalError` 组件在页面顶部展示全局错误。API 调用 catch 到的错误统一写入 store。

```tsx
// 页面布局
<GlobalError />     ← 页面顶部
<ErrorBoundary>     ← 兜底
  <PageContent />
</ErrorBoundary>
```

---

## 四、管道调度铁律

---

### ⑲ 状态只存 PG，结果只存 SQLite

**规则：** `processing_state`、`ai_engine_jobs.status` → PG。场景帧、标签、OCR、字幕 → SQLite。

**🔍 执行检查：**
```bash
grep -n "INSERT.*SQLite\|UPDATE.*SQLite\|scene\|Scene\b.*add\|subtitle\|Subtitle\b.*add" server/app/core/ server/app/api/
# 这些应该不在 PG 操作代码中出现
```

---

### ⑳ 管道状态的唯一写入口是 `job_helpers.set_job_status()`

**规则：** 所有状态更新走 `job_helpers.set_job_status()`，不直接写库。

```python
# ✅ 正确
from app.core.job_helpers import set_job_status
set_job_status(session, media_id, "scene", "completed")

# ❌ 禁止
cur.execute("UPDATE ai_engine_jobs SET status = 'completed' WHERE id = ?")
```

**🔍 执行检查：**
```bash
grep -rn "UPDATE.*ai_engine_jobs\|UPDATE.*processing_state" server/ --include="*.py" | grep -v "alembic\|migration"
# 如有输出，说明有绕过 job_helpers 的写操作
```

---

### ㉑ 前端展示依赖 `results_ready`，不依赖引擎状态

**规则：** 前端判断"有没有场景"应查 SQLite 中实际有多少条 scene 记录，不是查 `ai_engine_jobs.status`。

```json
GET /api/media/{id}/status
{
    "state": "completed",
    "results_ready": {
        "scenes": true,
        "ocr": false,
        "subtitle": true,
        "tags": true
    }
}
```

---

## 五、容器部署铁律

---

### ㉒ 明确持久化需求

| 容器 | 卷需求 |
|------|--------|
| postgres | PG data |
| reelmind-server | SQLite + 媒体库 |
| reelmind-orchestrator | 无（stateless） |
| reelmind-ai | 仅共享卷（媒体只读+SQLite 读写） |

---

### ㉓ AI 和 Orchestrator 必须 stateless

**规则：** 容器删了重建不影响任何数据。AI 模型权重预装在镜像里。

**🔍 执行检查：**
```bash
# 检查是否有容器写本地文件
grep -rn "open(\|write(\|\.save(\|\.to_json\|\.dump(" server/orchestrator/ server/ai_service/
# 确认这些路径都在挂载卷内，而非容器本地
```

---

### ㉔ 禁止 Docker socket 挂载

**规则：** 不允许将 `/var/run/docker.sock` 挂载到任何容器。这是容器逃逸的入口。

```yaml
# ❌ 禁止
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:rw
```

**🔍 执行检查：**
```bash
grep "docker.sock" docker-compose*.yml
# 有输出即违规
```

---

### ㉕ 日志与跨容器追踪（扩展规则升级为主铁律）

**规则：** 所有跨容器请求必须透传 `trace_id`，日志使用结构化格式，写到 stdout 不走文件。

```python
# 引入 structlog（推荐）
logger.info("pipeline_step", trace_id="abc123", engine="scene", step=5, total=10)
```

**🔍 执行检查：**
```bash
grep -rn "structlog\|get_logger.*trace_id" server/app/ server/ai_service/
# 如果没有 trace_id 注入，说明日志不可追踪
```

---

## 六、执行清单

### Code Review 必查项

```
[] ① Server 不调 AI 推理库（grep torch/transformers）
[] ② 新 api 文件 < 500 行
[] ⑤ 业务数据进了 store 吗（没用 useState 存 API 结果）
[] ⑥ 子组件用了 store 吗（没用 props 穿透）
[] ⑦ 组件有 loading/empty/error 三态
[] ⑧ 新路由页面有 ErrorBoundary
[] ⑨ 列表项组件有 React.memo
[] ⑩ 没往 app.ts 加新域
[] ⑪ 没留下 .bak 文件
[] ⑬ 没用硬编码中文
[] ⑰ 每个 catch 都有 setError
[] ⑳ 没直接写 ai_engine_jobs（用了 set_job_status）
[] ㉔ 没有 docker.sock 挂载
```

### CI 自动化检查

```yaml
# .github/workflows/check.yml 建议项
check:
  steps:
    - run: find web/src -name "*.bak" -o -name "*.refactor-backup" && exit 1 || true
    - run: pnpm typecheck
    - run: find server/app/api -name "*.py" -exec wc -l {} \; | awk '$1 > 500 && exit 1'
    - run: grep -rn "catch\s*{}" web/src/pages/ web/src/components/ | grep -v "video\.play" && exit 1 || true
    - run: grep "docker.sock" docker-compose*.yml && exit 1 || true
```

### 每周测量指标

| 指标 | 阈值 | 当前值 |
|------|------|--------|
| 后端 api 文件超 500 行数量 | < 3 | 5 |
| 前端页面组件超 500 行数量 | < 3 | 5 |
| 空 catch 数量 | 0 | ~15 |
| .bak 残留文件 | 0 | ~14 |
| 硬编码中文字符串 | 0 | ~10 |
| app.ts 行数 | < 200 | 460 |
| React.memo 数量 | > 3 | 0 |

---

## 七、开发执行标准

每做一次改动，按 **修改 → 执行 → 验收** 三步走。

---

### 一、修改标准

#### 规则：先思考，再出方案，验证后确认再修改

AI 在修改任何代码前，必须先执行以下验证步骤确认当前状态：

```bash
# 1. 确认当前环境状态
docker compose ps                    # 所有容器都在跑？
curl http://localhost:2588/api/ping  # API 通？
curl http://localhost:2589/health    # AI 服务通？

# 2. 确认要改的文件当前内容
# 用 Read 工具读取要修改的文件，确认当前内容
# 用 git diff / git status 了解当前改动状态

# 3. 确认改动的基线
# - 修 bug：先复现 bug，确认问题存在
# - 改行为：先确认当前行为
# - 重构：先确认测试通过
# - 做之前和做之后有明确对比依据
```

#### 新增文件规范

| 文件类型 | 放哪里 | 命名规范 |
|----------|--------|---------|
| Python API 路由 | `server/app/api/` | 蛇形命名，如 `tag_export.py` |
| Python 模型 | `server/app/models/` | 蛇形命名 |
| React 页面 | `web/src/pages/` | PascalCase，如 `VideoDetail.tsx` |
| React 组件 | `web/src/components/` | PascalCase，功能子目录分组 |
| Zustand store | `web/src/stores/` | 小驼峰，如 `videoStore.ts` |
| API 模块 | `web/src/api/` | 小驼峰，如 `videoApi.ts` |
| 文档 | `docs/` | 中文命名，`必读_` 前缀表示新人必读 |

#### 分支命名

```
feat/xxx       — 新功能
fix/xxx        — 修 bug
refactor/xxx   — 重构
chore/xxx      — 杂项（依赖、配置、CI）
```

#### Git Commit 规范

```
格式：<type>(<scope>): <subject>

type: feat / fix / refactor / style / docs / chore / perf / test
scope: server / web / ai / orchestrator / docker / docs

✅ 正确示例：
  feat(web): 添加视频批量删除功能
  fix(server): 修复扫描时 N+1 查询
  refactor(ai): 拆分 pipeline.py 引擎步骤
  chore(docker): 移除 docker.sock 挂载

❌ 禁止：
  update / fix bug / 改了点东西
```

#### 禁止行为

```
❌ 不验证就改代码
❌ 直接 push 到 main 分支
❌ 提交 .bak / .refactor-backup / .original 文件
❌ 在同一个 PR 中混入无关改动（修 bug 时顺带改格式 → 拆两个 PR）
❌ 空 commit message
```

---

### 二、执行标准（改完怎么跑）

#### 后端

```bash
# 改了 server/app/ 下的 .py 文件
# 容器有 --reload，改完等 2 秒自动生效，无需重启
# 如果改了依赖 requirements.txt，需要重建镜像
docker compose build reelmind-server
```

#### AI 服务

```bash
# 改了 server/ai_service/ 下的 .py 文件
# 容器有 --reload，改完等 2 秒自动生效
# 如果改了下游依赖
docker compose build reelmind-ai
```

#### 前端

```bash
# 开发模式（热重载，改完浏览器即时刷新）
cd web && npx vite --host 127.0.0.1 --port 5173

# 构建部署
cd web && npm run build
# 构建产物在 web/dist/，以 volume 挂载到容器，无需重启
```

#### 数据库迁移

```bash
# 如果改了 SQLAlchemy 模型，需要生成 migration
docker compose exec reelmind-server alembic revision --autogenerate -m "描述"
docker compose exec reelmind-server alembic upgrade head
# 容器启动时也会自动跑 alembic upgrade head
```

#### 代码格式化

```bash
# 后端 — 提交前必须跑
cd server && black --line-length=100 .

# 前端 — 提交前必须跑
cd web && npx prettier --write "src/**/*.{ts,tsx,css}"
```

---

### 三、验收标准（怎么确认改对了）

#### ① 功能验收

```
[ ] 改了的东西，功能符合预期吗？
    → 如果是修 bug：bug 不再复现
    → 如果是加功能：新功能按设计工作
    → 如果是重构：行为没变但代码更好了
[ ] API 通了吗？  curl http://localhost:2588/api/ping
[ ] AI 通了吗？   curl http://localhost:2589/health
```

#### ② 代码验收

```
[ ] pnpm typecheck                    # 前端无类型错误
[ ] black --check .                   # 后端格式合规
[ ] npx prettier --check .            # 前端格式合规
[ ] 没有新增空 catch                  # grep 无结果
[ ] 没有 .bak / .refactor-backup      # 无残留文件
[ ] 没有硬编码中文字符串              # 中文走 i18n
[ ] 涉及 ai_engine_jobs → 用了 set_job_status
[ ] 新 api 文件不超过 500 行
[ ] 新组件做了 loading/empty/error 三态
[ ] 新页面包了 ErrorBoundary
[ ] 新增文件放对了位置、命对了名
```

#### ③ 回归验收

```
[ ] 改了后端 → 现有主要前端页面正常显示
[ ] 改了前端 → 页面渲染正常，API 无 500
[ ] 改了模型 → migration 正常升级
[ ] 改了配置 → 容器重启后配置持久化
[ ] 改了什么 → 对应的 docs/ 文档更新了吗
```

#### ④ 最终确认

```
[ ] 从头看一遍自己改的 diff（git diff）
[ ] 和先验证时的基线对比，确认改的就是要改的
[ ] 没有遗留的调试代码（console.log / print / TODO）
```

---

## 一句话总结

**后端无状态代理、Zustand store 管数据、子组件自包含、空 catch 禁止、大文件必拆、死代码必清、高频组件加 memo、store 按域拆分、中文走 i18n、Docker socket 禁止挂载。** 铁律可用 `执行清单` 做 Code Review，用 `CI 自动化` 做防线，用 `每周指标` 追踪退化。
