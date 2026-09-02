# REELMIND 新工程师上手方案

> 目标：让一个对项目陌生的工程师在 **5 个工作日内** 具备独立开发能力。
> 前置要求：熟悉 Python FastAPI / React TypeScript / Docker 基础。

---

## 上手路线图

```
Day 1     Day 2          Day 3           Day 4          Day 5
├── 全景   ├── 后端走读    ├── 前端走读     ├── 实操任务    ├── 独立开发
│         │              │               │              │
阅读文档   核心 API       AI 页面架构     修一个 bug     领一个新功能
跑起来     DB 模型        Store 模式      加个小功能     走完 PR 流程
```

---

## Day 1 — 项目全景认知

### 1.1 阅读文档（2h）

按顺序读，不要跳：

1. **`CLAUDE.md`**（项目根）— 3 分钟看完架构概览
2. **`docs/REELMIND_INTRO.md`** — 容器架构、AI 管线、API 端点、数据库
3. **`REELMIND Web 架构铁律与执行手册.md`** — 重点看 25 条铁律和执行清单
4. **`REELMIND Web 架构铁律与优化建议.md`** — 了解历史问题和当前进度
5. **`REELMIND-全项目审查报告.md`** — 了解全貌和待改进项

**看完要能回答：**
- 项目有几个容器？各干什么？
- AI 管线顺序是什么？5 个模型按什么顺序跑？
- 数据怎么存？PG vs SQLite 各存什么？
- 前端用什么状态管理？API 调用层怎么组织的？

### 1.2 跑起来（2h）

```bash
# 1. 确认 Docker 在运行
docker ps

# 2. 进入项目目录
cd reelmind

# 3. 确认所有容器 Running
docker compose ps

# 4. 打开浏览器确认
# http://localhost:2588           → Web UI
# http://localhost:2589/health    → AI 健康检查

# 5. 启动前端开发模式
cd web
npx vite --host 127.0.0.1 --port 5173
# 浏览器 http://localhost:5173    → 前端热重载

# 6. 确认 API 通
curl http://localhost:2588/api/ping
curl http://localhost:2588/api/system/stats
```

### 1.3 动手探索（1h）

```bash
# 看日志
docker logs --tail 50 reelmind-server
docker logs --tail 50 reelmind-ai
docker logs --tail 50 reelmind-orchestrator

# 看看数据库里有什么
docker compose exec postgres psql -U reelmind -c "\dt"
docker compose exec postgres psql -U reelmind -c "SELECT count(*) FROM assets;"

# 看看 SQLite
docker compose exec reelmind-server ls /data/reelmind/
```

---

## Day 2 — 后端深度走读

### 2.1 API 路由地图（2h）

```bash
# 用 find 看一眼 api 目录结构
find server/app/api -name "*.py" | sort
```

跟着代码把一条完整请求链路走通：**前端点击「扫描媒体库」→ 触发扫描 → AI 管线启动 → 结果写 SQLite → 前端展示**

| 步骤 | 文件 | 关键函数 |
|------|------|---------|
| ① 前端点击 | `web/src/components/ai/AIPendingOverview.tsx` | 调 `handleScanLibrary` |
| ② API 调用 | `web/src/api/ai.ts` | `scanLibraryAI()` |
| ③ 后端路由 | `server/app/api/ai/scan.py` | `scan_library()` |
| ④ 转发到 AI | `server/app/core/proxy.py` | `_ai_post()` |
| ⑤ AI 处理 | `server/ai_service/main.py` | `/pipeline/start` |
| ⑥ 管线执行 | `server/ai_service/pipeline.py` | `AIPipeline.process_batch()` |
| ⑦ 结果写入 | `server/ai_service/models/ai_models.py` | SQLite ORM |
| ⑧ 前端读取 | `server/app/api/ai/process.py` | 从 SQLite 查询 |
| ⑨ 前端展示 | `web/src/stores/ai.ts` | `startPolling()` |

### 2.2 核心文件标注（2h）

打开编辑器，快速过一遍（不需要逐行读，了解结构就行）：

```python
# 必读
server/app/main.py              # FastAPI 入口——了解 middleware、CORS、路由注册
server/app/database.py           # 会话管理——async vs sync 怎么分的
server/app/config.py             # 配置——环境变量怎么加载
server/app/core/job_helpers.py   # 管道状态管理——set_job_status 怎么工作的

server/app/models/asset.py       # 主要 ORM 模型
server/app/models/ai_engine_job.py  # 管道作业模型
server/app/schemas/asset.py      # Pydantic 响应模型

server/app/api/ai/process.py     # AI 代理路由——forward 到 AI 容器的入口
server/app/api/ai/scan.py        # 扫描逻辑——scan-library / scan-status / pending-count
server/app/api/assets.py         # 资产 CRUD——最大的 api 文件

server/ai_service/main.py        # AI 容器入口——模型管理、管线触发
server/ai_service/pipeline.py    # 核心管线引擎——5 个模型的编排逻辑

server/orchestrator/main.py      # 调度器——轮询 PG 调度 AI 作业
```

### 2.3 数据库关系图（1h）

理解 PG 和 SQLite 的表关系：

```
PG: assets                <──> ai_engine_jobs (每个引擎一条记录)
     |                          - media_id
     |                          - engine_name (scene/yolo/ocr/clip/whisper/diarization)
     |                          - status (pending/running/completed/error)
     |                          - depends_on
     |
     └── library         ─── libraries
     └── tags             <──> asset_tags (多对多)

SQLite: videos  <──> scenes  <──> scene_tags
                        |     <──> scene_ocr
                        |     <──> frames (CLIP embeddings)
              <──> subtitles
```

---

## Day 3 — 前端深度走读

### 3.1 前端地图（2h）

```
web/src/
├── App.tsx              # 路由定义——看有哪些路由和 ErrorBoundary
├── api/                 # API 调用层
│   ├── base.ts          # 通用 request() + token 注入
│   ├── client.ts        # barrel 导出
│   ├── ai.ts            # AI 相关 API
│   └── assets.ts        # 资产相关 API
├── stores/              # 状态管理（Zustand）
│   ├── app.ts           # 全局状态（auth/libraries/search...）
│   ├── ai.ts            # AI 引擎状态 + 轮询 + SSE
├── pages/               # 页面组件
│   ├── AIEnginePage.tsx # AI 引擎页——看怎么组合子组件
│   ├── AssetGrid.tsx    # 资产列表页——看虚拟滚动 + 筛选
│   └── AssetDetailV2.tsx# 资产详情页——看场景/字幕展示
├── components/ai/       # AI 子组件
│   ├── AIPendingOverview.tsx  # 待处理概览
│   ├── AIModelStatus.tsx     # 模型状态
│   ├── GPUInfo.tsx           # GPU 信息
│   ├── PipelineConfigPanel.tsx # 管线配置
│   └── AIPipelineConfig/    # 配置子组件
```

### 3.2 理解状态管理模式（1h）

Zustand 模式是前端的核心，花时间理解：

```typescript
// 模式：store 定义
interface AIStore {
  // 状态
  pendingCounts: PendingCounts | null
  queueStatus: QueueItem[]
  error: string | null

  // 动作（直接写 store）
  fetchPendingCount: () => Promise<void>
  handleScanLibrary: () => Promise<void>
  startPolling: () => void
}

// 模式：组件使用
function GPUInfo() {
  const gpuInfo = useAIStore(s => s.gpuInfo)        // 选择器粒度控制
  const loading = useAIStore(s => s.gpuInfoLoading)  // 重渲染范围

  if (loading) return <SkeletonCard />
  if (!gpuInfo) return <div className="text-gray-500">无数据</div>
  return <div>...</div>
}
```

重点关注 **铁律⑤⑥⑦** 在代码中是怎么体现的。

### 3.3 调试工具链（1h）

```bash
# 前端调试
# 1. Vite 开发服务器
cd web && npx vite --host 127.0.0.1 --port 5173

# 2. F12 Network 面板看 API 请求
# 3. React DevTools 看组件树和 props
# 4. sources 面板打断点

# 后端调试
# 加 print() 看 docker logs
docker logs --tail 20 -f reelmind-server

# 或者
docker compose exec reelmind-server python -c "print('hello')"
```

---

## Day 4 — 第一个实操任务

从易到难选一个做：

### 🟢 简单：修一个违反铁律的 catch

```bash
# 找到空 catch
grep -rn "catch\s*{}" web/src/pages/ web/src/components/ | grep -v "video\.play"
```

打开文件，把空 `catch {}` 改成 `catch (e) { setError("连接服务器失败") }`。
提交 PR，在描述里引用铁律⑩。

### 🟡 中等：排查一个 N+1 查询

```bash
# 在 search.py 中加 selectinload
grep -n "selectinload" server/app/api/search.py
```

如果在 search 路由中发现延迟加载，加上 `selectinload`，确认前端的列表请求响应时间下降。

### 🔴 挑战：合并 pending-count 和 scan-status 轮询

当前 `stores/ai.ts:startPolling()` 有两个独立的 3s 轮询，改成用一个 3s 定时器，一个请求拿回两个数据。

### 提交标准

```
1. 代码通过 linter（有的话）或至少自测
2. 没有新增空 catch
3. PR 描述写明改了啥、为什么改、对应哪条铁律
4. 没有残留 .bak 文件
```

---

## Day 5 — 独立开发准备

### 5.1 PR 流程

```
1. git checkout -b feat/xxx
2. 改代码
3. pnpm typecheck         # 前端类型检查
4. docker compose build reelmind-server  # 后端重建
5. 自测
6. git commit -m "feat: xxx"
7. git push
8. 提 PR → Code Review → 合并
```

### 5.2 排错速查表

| 现象 | 排查步骤 |
|------|---------|
| 前端白屏 | F12 Console 看报错 → 是不是 Error Boundary 没包 → 空 catch 吞了错误 |
| 前端 404 | 看 Network 面板请求路径 → 是不是 Vite proxy 没配 |
| API 返回 500 | `docker logs reelmind-server` 看 traceback |
| 管道卡住不动 | `docker logs reelmind-ai` → 查 `ai_engine_jobs` 表状态 |
| GPU 跑满 | `nvidia-smi` → `docker logs reelmind-ai` 看哪个模型在跑 |
| 前端数据不更新 | 看 Network 面板轮询请求是不是 304 → store 是不是没 setState |
| 数据库连接失败 | `docker compose logs postgres` → 检查 `.env` 中 DB 配置 |
| 镜像构建慢 | `docker compose build --no-cache reelmind-ai` → 需要翻墙下载模型 |

### 5.3 铁律违反自查

提交代码前跑一遍（可以加到 git hook）：

```bash
echo "=== 检查 .bak 文件 ==="
find web/src -name "*.bak" -o -name "*.refactor-backup" && echo "⚠️ 有残留" || echo "✅"

echo "=== 检查 docker socket ==="
grep "docker.sock" docker-compose*.yml && echo "⚠️ 有挂载" || echo "✅"

echo "=== 检查空 catch ==="
grep -rn "catch\s*{}" web/src/pages/ web/src/components/ | grep -v "video\.play" && echo "⚠️ 有空 catch" || echo "✅"
```

---

## 参考文档索引

## 参考文档阅读顺序

| 优先级 | 文档 | 原因 |
|--------|------|------|
| 🔴 必读 #1 | `必读_README.md` | 项目定位、功能概览、快速启动命令 |
| 🔴 必读 #2 | `必读_REELMIND Web 架构铁律与执行手册.md` | **25 条铁律 + 执行检查 + CI 清单，开发必须遵守** |
| 🔴 必读 #3 | `必读_NEW_ENGINEER_ONBOARDING.md` | 5 天上手方案、代码走读路线、排错速查表 |
| 🟡 需要时 | `REELMIND_INTRO.md` | 想了解容器架构细节、AI 管线、数据库表时 |
| 🟡 需要时 | `前端调试方法和流程.md` | 跑前端开发模式、调 API 代理时 |
| 🟡 需要时 | `REELMIND 视觉设计原则与规则.md` | 写前端组件、做 UI 改动时 |
| 🟡 需要时 | `REELMIND的容器关系.md` | 想理解架构拆分的历史背景时 |
| ⚪ 参考 | `CLAUDE.md` | 项目全局上下文，AI 自动读取。人也偶尔翻翻 |

## 常见问题

**Q: 改前端代码怎么看效果？**
A: 跑 `npx vite` 开热重载，不需要重启 Docker。

**Q: 改了后端代码怎么看效果？**
A: `server/` 和 `server/ai_service/` 以 volume 挂载到容器，有 `--reload` 参数，改完等 2 秒自动生效。

**Q: 改了 Python 依赖怎么办？**
A: 需要 `docker compose build reelmind-server` 或 `docker compose build reelmind-ai`。

**Q: 怎么连数据库？**
A: `docker compose exec postgres psql -U reelmind`。

**Q: 数据库迁移怎么弄？**
A: 容器启动时自动跑 `alembic upgrade head`。新增 migration 后重启 server 容器即可：
`docker compose restart reelmind-server`。