# REELMIND 发布 GitHub：全面检查结论与提交方案

> 日期：2026-09-02
> 状态：🟡 待确认（仅审计 + 方案，未提交、未改代码）
> 目标：把当前仓库安全、干净地发布到 `github.com/JiaZhouZhaiShen/reelmind`，并沉淀一套后续多项目发布清单

---

## 一、发布就绪度审计结论（只读实测）

| 检查项 | 结果 |
|--------|------|
| 真实密钥/Token/私钥 | ✅ 未发现。`.env.example` 全为 `change-me` 占位符；无 `ghp_`/`sk-`/`AKIA`/PRIVATE KEY |
| 大文件入库 | ✅ 无 >1MB 跟踪文件 |
| 敏感目录入库 | ✅ `data/`、`media/`、`backups/`、`node_modules/`、`web/dist/`、`torch_wheels/` 均未入库 |
| `.env` 真实配置 | ✅ 未被跟踪（`.gitignore` 保留排除） |
| LICENSE | ✅ MIT（2024 ReelMind Contributors） |
| 当前推送状态 | ✅ 全部提交已推送到 `github/main`（私有仓库已建） |
| 暂存区 | 仅 `.env.example` 已暂存；`.gitignore`、修订记录、新部署文档未提交 |

---

## 二、审计发现清单

### 🔴 建议处理（公开前）

1. **根目录 5 个调试脚本已入库且无引用**：
   - `_batch_a_all.py` / `_batch_a_format.py` / `_batch_a_i18n.py` / `_batch_a_stores.py`（一次性 i18n 批量工具）
   - `test_scene.py`（含本机 NAS 路径 `/nas-media/PR视频/...`，属于测试残留）
   - 全仓代码无引用，建议删除后提交。历史仍保留旧版本；如需历史级清理见第 4 条。

2. **仓库没有根 README.md**：GitHub 首页会空白。建议新增根 README（简介、5 容器架构、快速开始、文档索引）。

3. **未入库的新部署文档**：`docs/必读_项目介绍与部署指南.md`（12:48 生成，clone 部署指南）应随本次提交；其内容含 `cd D:\DockerData\reelmind # 或你的项目路径`，建议顺手改为 `cd reelmind`（clone 后语境）。

4. **历史级垃圾文件**：更早提交里存在调试脚本/截图等。要彻底清除需 `git filter-repo` 重写历史，会改变所有 commit hash 并影响 Synology `origin` 同步。**首轮不建议做**；若未来转公开且介意历史，再单独立项。

### 🟡 可选处理（不阻塞发布）

5. 文档里散落本机路径 `D:\DockerData\reelmind`（CLAUDE.md、onboarding、方案文档、0704 逻辑文档）。私有阶段无妨；转公开前建议泛化为 `reelmind/` 相对写法。
6. `docker-compose.yml` / `config.py` 含开发默认值 `reelmind`、`reelmind-dev-secret-change-me-in-production`。已带红色警告注释且非真实凭据，可发布；README 中应写明“首次部署必须替换”。

---

## 三、提交方案（建议分批提交，Commit 0 行尾基线 + 8 个 commit + 发布配套）

### Commit A：入库环境模板

```powershell
git add .gitignore .env.example
git commit -m "chore: 入库 .env.example 环境模板（占位符，无真实密钥）"
```

内容：`.gitignore` 取消忽略 `.env.example` + 新增 `.env.example`。

### Commit B：新部署指南 + 修订记录

```powershell
git add "docs/必读_项目介绍与部署指南.md" "docs/铁律修订记录.md"
git commit -m "docs: 部署指南与铁律修订记录（含 GitHub clone 部署须知）"
```

内容：并发产物的部署指南入库；修订记录含多期变更（阶段一/二、clone 可用性修复等），故提交信息用宽口径。建议先把指南里的 `D:\DockerData\reelmind` 改成 clone 后相对路径。

### Commit C：新增根 README

```powershell
git add README.md
git commit -m "docs: 新增根 README（项目简介与快速开始）"
```

前置：新建根 `README.md`，内容从 `docs/必读_README.md` / 部署指南提炼：项目定位、5 容器表、快速开始、clone 后 `.env` 配置、文档索引、MIT。

### Commit D（可选）：清理根目录调试脚本

```powershell
git rm _batch_a_all.py _batch_a_format.py _batch_a_i18n.py _batch_a_stores.py test_scene.py
git commit -m "chore: 清理根目录一次性调试脚本"
```

前置：已确认全仓无引用（`rg` 实测）。删除前无需备份（git 历史可恢复）；若你仍想保留，可先复制到 `backups/`。

### Commit E：英文文档镜像（开源门面）

```powershell
git add docs/en/
git commit -m "docs(en): 铁律/规范/部署指南英文镜像"
```

内容：`docs/en/IRON_RULES.md`、`docs/en/STANDARDS/00-08`、`docs/en/PROJECT_GUIDE.md`（对应 `docs/铁律.md`、`docs/规范/00-08`、`docs/必读_项目介绍与部署指南.md`；中文为唯一真相源，英文文件头部注明翻译）。**已全部完成（11 个文件）**，随 Commit E 一并入库；开源社区英文铁律是必要文档，不遗漏在 untracked。

### Commit H（可选，推荐）：提交方案文档

```powershell
git add "docs/方案_REELMIND发布GitHub提交方案_2026-09-02.md"
git commit -m "docs: REELMIND 发布 GitHub 审计与提交方案"
```

内容：把本方案文档自身入库（与 `docs/方案_*.md` 入库惯例一致），后续可追溯决策；如想留在本地不入库也可跳过。

### Commit F：社区与协作配套（.github）

```powershell
git add .github/
git commit -m "docs: 新增 CONTRIBUTING/CODE_OF_CONDUCT/SECURITY 与 issue/PR 模板"
```

内容：`.github/CONTRIBUTING.md`、`.github/CODE_OF_CONDUCT.md`、`.github/SECURITY.md`、issue 模板（bug/feature）、PR 模板（含铁律自查勾选：check.sh 13 项、typecheck、无密钥）。

### Commit G：CI 质量门禁（GitHub Actions）

```powershell
git add .github/workflows/
git commit -m "ci: 新增铁律检查/typecheck/build 工作流"
```

内容：`.github/workflows/ci.yml`，push/PR 时跑：`./scripts/check.sh`、`cd web && npm run typecheck`、`cd web && npm run build`。铁律 13 项检查变成公开绿色徽章。

### 发布配套（发布日执行，非 commit）

- README 补截图/demo（建议 `docs/images/` 放 2-3 张真实截图）+ shields badges（build/typecheck/license）
- `gh repo edit reelmind --description "..." --add-topic self-hosted --add-topic video-library --add-topic ai --add-topic semantic-search`
- 打 tag：`git tag v0.1.0 && git push github main --tags`，写 GitHub Release notes
- 本机路径清理（Commit B 一并处理 `D:\DockerData\reelmind` -> `reelmind`）
- GHCR/镜像发布：**后续立项**（当前全部本地 build 劝退尝鲜者；推镜像后用户可 `docker compose up`）

### 工作区现状与 add 纪律（执行前必读）

实测（2026-09-02）：`git status` 显示 187 个 ` M` 文件——**全部是行尾假象**（工作区源码为 CRLF，HEAD index 为 LF），忽略行尾后真实改动仅 2 个（`.gitignore`、`docs/铁律修订记录.md`）。仓库无 `.gitattributes`，行尾策略未声明。**执行前必须先建行尾基线，否则任何 `git add` 都会把该文件的行尾 CRLF→LF 转换一起带入，产生脏 diff。**

**行尾基线步骤（Commit 0，最先执行）：**

```powershell
# 0. 先清空暂存区（当前已暂存 .env.example，避免与 renormalize 混合）
git reset

# 1. 新建 .gitattributes（LF 策略，跨平台统一）
#    内容见下框

# 2. 归一化全部入库文件行尾到 LF（一次性）
git add --renormalize .
git commit -m "chore: 声明 .gitattributes（LF 行尾策略）并归一化全仓"

# 3. 归一化后继续 Commit A（此时 .env.example 由 Commit A 一并入库）
```

`.gitattributes` 内容：

```
* text=auto
*.py text eol=lf
*.ts text eol=lf
*.tsx text eol=lf
*.js text eol=lf
*.jsx text eol=lf
*.md text eol=lf
*.sh text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.json text eol=lf
*.css text eol=lf
*.html text eol=lf
*.txt text eol=lf
*.pyi text eol=lf
*.db binary
*.png binary
*.jpg binary
*.jpeg binary
*.webp binary
*.ico binary
*.woff binary
*.woff2 binary
```

> 行尾基线建立后，`git status` 应干净；此后每个 Commit 只 `git add` 该 Commit 列出的路径，禁止 `git add -A`；若再出现新的 ` M`/`??`，先归入对应 Commit 或报告，不擅自提交。

### 推送

```powershell
git push github main
```

---

## 四、不提交清单

- ❌ `.env`（真实配置，保持 gitignore）
- ❌ `backups/`、`data/`、`media/`、`node_modules/`、`web/dist/`、`torch_wheels/`
- ❌ 根目录未入库的临时文件（`fix_*`、`tmp_*`、截图、日志等，多数已被忽略）
- ❌ 若不做历史清洗：已有提交中的旧调试文件（保持现状）

---

## 五、发布后核对

1. GitHub 页面确认无 `.env`、无 `.bak`、无 `backups/`。
2. `git ls-files | grep -E "\.env$|\.bak|^backups/"` 应为空。
3. README 渲染正常，仓库描述/主题可顺手补充。
4. 切 Public 前再跑一次密钥扫描（复用本方案检查项），并处理可选问题 5/6。
5. Actions 首次运行通过（3 个 job 全绿）。
6. 提交信息均为 Conventional Commits，历史无中间调试态。
7. Release v0.1.0 发布后检查 GitHub 搜索 topics 可命中。

---

## 六、待确认决策

| # | 决策 | 推荐 |
|---|------|------|
| D1 | Commit D 是否本轮执行（删 5 个调试脚本） | 执行（无引用、属测试残留） |
| D2 | 根 README 本轮新建还是后续补 | 本轮新建（Commit C） |
| D3 | 仓库保持 Private 还是切 Public | 先 Private，稳定后再 Public |
| D4 | 历史是否 filter-repo 清洗 | 首轮不做 |
| D5 | `.github` 模板 + CI 是否本轮一并提交 | 本轮提交（Commit F/G） |
| D6 | GHCR/镜像发布是否现在立项 | 后续立项，不阻塞本轮 |

---

## 八、开源推广与曝光清单（切 Public 后）

1. 提交质量：保持 Conventional Commits + 原子提交；每 commit 只做一件事。
2. 提交安全：push 前密钥扫描；`.env`/`backups/`/`.bak` 永远不入暂存区。
3. 版本节奏：功能稳定后打 tag + Release notes，形成可追溯版本。
4. 文档语言：README 与核心文档英文优先（本方案 Commit E），中文做镜像。
5. 社区入口：awesome-selfhosted、r/selfhosted、HN；中文区 V2EX/掘金/知乎/少数派。
6. 演示价值：真实截图/录屏 demo；说明无 GPU 也可用（关 AI 只做管理/搜索）。
7. 活跃度：及时回 issue/PR，模板化协作（Commit F）降低贡献门槛。
8. 镜像发布：GHCR 推 5 个自建镜像，实现 clone + `docker compose up` 即用（后续）。

---

## 七、后续多项目发布清单（通用）

```powershell
cd <项目目录>
# 1. 本地就绪
git branch -M main
# 2. 建仓推送（私有起步）
gh repo create <项目名> --private --source=. --remote=github --push
# 3. 核对
gh repo view <项目名>
```

每个项目发布前固定检查：
- `.env.example` 入库且为占位符；`.env` 排除
- 无真实 token/私钥（`rg` 扫 `ghp_|sk-|AKIA|PRIVATE KEY`）
- 无 >1MB 或 `node_modules/`/`media/`/`data/` 入库
- 根 README + LICENSE 存在
- 无本机绝对路径（`D:\`、`/nas-`、`192.168.x`）泄漏
- 清理调试脚本后再 push
