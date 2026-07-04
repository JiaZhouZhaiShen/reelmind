# HANDOFF：REELMIND 架构铁律执行进度

> 生成日期：2026-07-03
> 目标：逐条执行 `必读_REELMIND Web 架构铁律与执行手册.md`

---

## 总体进度

| 阶段 | 状态 | 说明 |
|------|------|------|
| Rule ⑤ 业务状态归 Store | ✅ **已完成** | 5/5 违规修复 |
| Rule ⑥ 子组件不从父组件接收业务 props | ✅ **已完成** | 2/2 违规修复 |
| Rule ⑦ 子组件自包含 loading/error/empty | ✅ **已完成** | 1 个修复，11 个排查 |
| Rule ⑧ 整页 ErrorBoundary | ✅ **已完成** | 16/16 路由全部包裹 |
| Rule ⑨ 高频组件加 React.memo | ✅ **已完成并验证** | 9 个组件添加，tsc --noEmit 零错误 |
| Rule ⑪ 清理死代码和重构残留 | ✅ **已完成** | 删除 14 个残留文件，tsc --noEmit 零错误 |
| Rule ⑫ TypeScript 严格检查 | ✅ **已完成** | 开启 noUnusedLocals / noUnusedParameters，修复 55 处 |
| Rule ⑩ Store 按 domain 拆分 | ✅ **已完成并验证** | app.ts 15行；新建 library/directory/tag/admin 4 个 store |
| Rule ⑬ i18n | ✅ **已完成并验证** | 32 文件 (第一批4 + 第二批7 + 第三批9 + 第四批3 + 第五批9)，tsc 零错误 |
| Rule ⑭ 构建分包 | ✅ **已完成** | sourcemap 条件化 + manualChunks |
| Rule ⑮ 页面≤500行 | ✅ **已完成** | LibraryManager 568→377行 |
| Rule ⑯ API 按域拆分 | ✅ **已完成** | 审计确认 `api/` 按域拆分合规，`client.ts` 20 行 barrel 导出 |
| Rule ⑰ 禁止空 catch | ✅ **已完成并验证** | 修复 PipelineConfigPanel.tsx 4 处空 catch，tsc 零错误 |
| Rule ⑱ 统一错误展示 | ✅ **已完成** | app.ts 添加 setError，GlobalError 接入完整 |
| Rule ⑲—㉕ | ✅ **已完成 (AssetDetailV2.tsx)** | /ai/results-ready 轮询 + i18n 30处 |

---

## Rule ⑤—⑧ 明细

参见上一版本。

---

## Rule ⑨：高频组件加 React.memo 保护

**状态：✅ 已完成并验证 (tsc --noEmit 零错误)**

全项目之前仅 1 个组件有 `React.memo`（VideoPlayer），现新增 9 个：

| # | 组件 | import 改动 |
|---|------|-----------|
| 1 | `VideoCard.tsx` | `{ useState }` → `{ useState, memo }` |
| 2 | `SearchVideoCard.tsx` | `{ useState }` → `{ useState, memo }` |
| 3 | `Sidebar.tsx` | 新增 `import { memo } from 'react'` |
| 4 | `AIPendingOverview.tsx` | 新增 `import { memo } from 'react'` |
| 5 | `GPUInfo.tsx` | 新增 `import { memo } from 'react'` |
| 6 | `AIModelStatus.tsx` | 新增 `import { memo } from 'react'` |
| 7 | `AIModelStatusCard.tsx` | 新增 `import { memo } from 'react'` |
| 8 | `ContainerStatusCard.tsx` | `{ useEffect, useRef }` → `{ useEffect, useRef, memo }` |
| 9 | `GPUStatusCard.tsx` | `{ useEffect, useRef, useState }` → `{ useEffect, useRef, useState, memo }` |

---

## Rule ⑪：清理死代码和重构残留

**状态：✅ 已完成 (tsc --noEmit 零错误)**

**清理清单：**
- 根目录：`_vp_bak.tsx`（0字节）、`_migrate_types.py`（0字节）
- 后端备份：`server/app/api/ai.py.bak2`、`ai.py.original`、`ai.py.refactor-backup`
- 前端死代码组件：`SearchResultCard.tsx`（零引用）、`AIStatsCards.tsx`（零引用）
- 测试残留：`web/_tmp_*.json` x7
- web/src 内部：无 .bak/.original 残留 ✅

---

## Rule ⑫：TypeScript 严格检查

**状态：✅ 已完成 (tsc --noEmit 零错误)**

**改动：**
- `tsconfig.json`：`noUnusedLocals: false` → `true`，`noUnusedParameters: false` → `true`
- 修复 22 个文件，共 55 处未用代码

**修复统计：**

| 文件 | 问题数 | 修复方式 |
|------|--------|---------|
| `api/client.ts` | 1 | 删未用 BASE |
| `App.tsx` | 1 | 删未用 user |
| `components/ai/AIModuleConfigPanel.tsx` | 1 | 删未用 MODULE_IDS |
| `components/ai/AISettings.tsx` | 1 | 删未用 SettingsIcon |
| `components/ai/BatchProgressSection.tsx` | 3 | 删未用变量 |
| `components/ai/PipelineConfigPanel.tsx` | 2 | 删 RefreshCw + resetMsg 状态 |
| `components/dashboard/ContainerStatusCard.tsx` | 1 | 删未用 cpuDisplay |
| `components/MetadataPanel.tsx` | 2 | 删 Asset interface + assetId prop |
| `components/Sidebar.tsx` | 2 | 删 api import + loadAssets |
| `components/VideoPlayer.tsx` | 1 | 删未用常量 |
| `pages/Admin/Dashboard.tsx` | 1 | 删未用 systemStatus |
| `pages/Admin/JobManagement.tsx` | 1 | 删未用 AdminJob |
| `pages/Admin/LogViewer.tsx` | 5 | 删未用函数/interface |
| `pages/AssetGridFilters.tsx` | 2 | 删未用 fetchPage/gridPage |
| `pages/AssetGridUtils.tsx` | 11 | 删 9 个未用 icon + PAGE_SIZE/OVERSCAN |
| `pages/AssetGridVirtual.tsx` | 3 | 删 GRID_ROW_HEIGHT/gridHasMore/scrollRAfRef |
| `pages/DirectoryView.tsx` | 2 | 删 Download/useNavigate |
| `pages/LibraryManager.tsx` | 7 | 删 4 icon + ScanJobInfo + 3 变量 |
| `pages/SearchPage.tsx` | 2 | 删 Search icon + t |
| `pages/TagBrowse.tsx` | 3 | 删 Hash/Download + TagCategory |
| `pages/TagManager.tsx` | 2 | 删 Layers + category 参数加 _ |
| `stores/logs.ts` | 1 | 删未用 TAIL_OPTIONS |

---

## Rule ⑩：Store 按 domain 拆分

**状态：✅ 已完成并验证 (tsc --noEmit 零错误)**

**改动：**
`app.ts` 从 153 行精简为 **12 行**，仅保留跨域共享的 `error`、`clearError`、`assetsById`。

新建 4 个 store：

| Store | 行数 | 职责 |
|-------|------|------|
| `library.ts` | 36 | libraries、selectedLibraryId、stats |
| `directory.ts` | 34 | dirTree、dirSubdirs |
| `tag.ts` | 53 | tagCategories、tagEntries、tagAllEntries |
| `admin.ts` | 38 | adminDashboard、systemStatus |

**跨 store 引用修复：**
- `asset.ts` — `useAppStore.getState().selectedLibraryId` → `useLibraryStore.getState().selectedLibraryId`
- `grid.ts` — 同上
- `search.ts` — 同上

**组件 import 迁移（14 个文件）：**
| 组件 | 旧 store | 新 store |
|------|---------|---------|
| Sidebar, LibraryManager, AssetGrid, AssetGridFilters, TimelineView, App.tsx | useStore → | useLibraryStore |
| Dashboard, AIModelStatusCard, ContainerStatusCard, GPUStatusCard | useStore → | useAdminStore |
| DirectoryView | useStore → | useLibraryStore + useDirectoryStore |
| TagBrowse | useStore → | useTagStore |

---

## 待处理规则

### Rule ⑬：i18n 禁止硬编码中文字符串
**状态：✅ 全部已完成并验证 (tsc --noEmit 零错误)**

**第一批（4 文件）

| 文件 | 替换数 | 说明 |
|------|--------|------|
| BatchToolbar.tsx | 13 | 按钮文本、confirm 提示、计数 |
| SearchVideoCard.tsx | 14 | 方向标签、title 属性、状态文字 |
| ErrorBoundary.tsx | 3 | 标题、错误消息、重试按钮 (class组件, i18n.t) |
| GlobalError.tsx | 1 | aria-label |

**新增 i18n key：** atchToolbar.* x13, searchVideoCard.* x14, rrorBoundary.* x3, globalError.* x1 — 共 31 个 key

**第二批（7 文件）状态：✅ 已完成并验证 (tsc --noEmit 零错误)**

| 文件 | 替换数 | 说明 |
|------|--------|------|
| AIModelStatusCard.tsx | 9 | 模块描述 + 状态文本 → i18n |
| ContainerStatusCard.tsx | 4 | 检测中、内存、运行中/已停止 |
| GPUStatusCard.tsx | 5 | GPU 状态、总显存占用等 |
| Dashboard.tsx | 7 | 系统监控、SER/AI 容器标签 |
| ErrorDashboard.tsx | 13 | diagnostics、SmallCard 标题 |
| JobManagement.tsx | 6 | cleanup、search placeholder |
| LogViewer.tsx | 31 | browse、search、source、columns 等 |

**新增 i18n key：** aiModel.* x9, containerStatus.* x4, gpuStatus.* x5, dashboard.* x7, errorDashboard.* x13, jobManagement.* x6, logViewer.* x31 — 共 75 个 key


### Rule ⑬ (第四批—3 panel files)
- `web/src/components/ai/AIModuleConfigPanel.tsx`
- `web/src/components/ai/PipelineConfigPanel.tsx`
- `web/src/pages/DirectoryView.tsx`
- `web/src/i18n/locales/en.json` (新增 ~113 个 key)

### Rule ⑬ (第五批—9 文件收尾)
**状态：✅ 已完成并验证 (tsc --noEmit 零错误)**

| 文件 | 替换数 | 说明 |
|------|--------|------|
| AssetGridFilters.tsx | ~17 | 方向/排序/筛选/归档按钮 → common.*, filter.* (0 新 key) |
| AssetGridVirtual.tsx | ~10 | 未归类/定位/空状态/加载文字 ← 4 新 key |
| SearchPage.tsx | ~14 | 搜索结果/来源筛选/方向按钮 ← 4 新 key |
| VideoCard.tsx | 6 | 方向标签/状态文字/AI标识 title → common.* (0 新 key) |
| TagBrowse.tsx | 3 | 方向筛选按钮 → common.* (0 新 key) |
| TimelineView.tsx | 6 | 4 错误消息 + 全选当天/滚动加载 ← 6 新 key |
| ProcessedAssets.tsx | 8 | FILTER_DEFS 改用 labelKey + 标题/空状态 ← 8 新 key |
| BatchProgressSection.tsx | ~15 | 引擎名/状态/摘要行 ← 10 新 key |

**新增 i18n key：** assetGridVirtual.* x4, searchPage.* x4, timelineView.* x6, processedAssets.* x8, batchProgress.* x10 — **共 ~32 个 key**

- `web/src/i18n/locales/zh.json` (新增 ~113 个 key)

### Rule ⑬ (第三批—stores + format.ts i18n)

**状态：✅ 已完成并验证 (tsc --noEmit 零错误)**

| 文件 | 替换数 | 说明 |
|------|--------|------|
| stores/asset.ts | 4 | loadFailed 错误消息 → i18n |
| stores/ai.ts | 2 | loadFailed、sseDisconnected → i18n |
| stores/admin.ts | 2 | loadFailed、connFailed → i18n |
| stores/adminJobs.ts | 4 | loadFailed、retryFailed、cancelFailed、cleanupFailed → i18n |
| stores/library.ts | 2 | loadFailed、searchFailed → i18n（含 searchRetry）|
| stores/logs.ts | 2 | logLoadFailed、logSourceLoadFailed → i18n |
| stores/search.ts | 1 | searchRetry → i18n |
| stores/grid.ts | 1 | yearLoadFailed → i18n |
| utils/format.ts | 6 | formatRelativeTime 中时间文字 → t() |

**新增 i18n key：** format.* x6 (justNow, secondsAgo, minutesAgo, hoursAgo, monthDay, yearMonth), store.* x11 (loadFailed, connFailed, sseDisconnected, retryFailed, cancelFailed, cleanupFailed, searchFailed, searchRetry, yearLoadFailed, logLoadFailed, logSourceLoadFailed) — **共 17 个 key**


### Rule ⑬ (第四批—3 panel files)

**状态：✅ 已完成并验证 (tsc --noEmit 零错误)**

| 文件 | keys | 说明 |
|------|------|------|
| AIModuleConfigPanel.tsx | ~55 | aiModuleConfig.* — 6 模块 × (label/desc + fields) + 通用状态 |
| PipelineConfigPanel.tsx | ~40 | pipelineConfig.* — 3 tabs, 6 engines, 参数标签, 按钮/状态 |
| DirectoryView.tsx | ~18 | directoryView.* — 空状态、错误消息、排序、加载文本 |

**新增 i18n key：** aiModuleConfig.* ~55, pipelineConfig.* ~40, directoryView.* ~18 — **共 ~113 个 key**


### Rule ⑭：构建分包配置
**状态：✅ 已完成** | sourcemap 条件化 + manualChunks(vendor/state/i18n)

### Rule ⑮：页面组件不超过 500 行
**状态：✅ 已完成** | LibraryManager.tsx 568→377行；拆出 LibraryCard + LibraryEditDialog

### Rule ⑯：API 按域拆分文件
**状态：✅ 已完成** | 审计确认 `web/src/api/` 目录结构符合要求

### Rule ⑰：禁止空 catch
**状态：✅ 已完成并验证 (tsc --noEmit 零错误)** | 修复 `PipelineConfigPanel.tsx` 4 处空 catch

| # | 位置 | 修复方式 |
|---|------|---------|
| 1 | `loadPendingCount` (L77) | `console.warn` + `useStore.getState().setError()` |
| 2 | `loadCheckpoints` (L84) | `console.warn` + `useStore.getState().setError()` |
| 3 | polling `getBatchEngineProgress` (L131) | `console.warn`（轮询错误不弹全局 banner） |
| 4 | `handleResetErrors` (L167) | `console.error` + `useStore.getState().setError()` |

### Rule ⑱：统一错误展示
**状态：✅ 已完成** | app.ts 添加 `setError` action，GlobalError 接入完整

### Rule ⑲—㉕：AssetDetailV2.tsx
**状态：✅ 已完成 (tsc --noEmit 零错误)**

| 规则 | 工作内容 |
|------|------|
| ⑬ | 30处硬编码中文→i18n |
| ㉑ | 轮询改用 /ai/results-ready API |

---

## 修改的文件清单（累计）

### Rule ⑤
- `web/src/stores/app.ts` / `web/src/pages/TagBrowse.tsx` + 4 个之前会话完成的文件

### Rule ⑥
- `web/src/components/YearTimeline.tsx` / `web/src/pages/TimelineView.tsx` / `web/src/pages/AssetGrid.tsx`
- `web/src/components/SearchVideoCard.tsx` / `web/src/pages/SearchPage.tsx`

### Rule ⑦
- `web/src/components/ai/AutoRunProgressBar.tsx`

### Rule ⑧
- `web/src/App.tsx`

### Rule ⑨
- `web/src/components/VideoCard.tsx`
- `web/src/components/SearchVideoCard.tsx`
- `web/src/components/Sidebar.tsx`
- `web/src/components/ai/AIPendingOverview.tsx`
- `web/src/components/ai/GPUInfo.tsx`
- `web/src/components/ai/AIModelStatus.tsx`
- `web/src/components/dashboard/AIModelStatusCard.tsx`
- `web/src/components/dashboard/ContainerStatusCard.tsx`
- `web/src/components/dashboard/GPUStatusCard.tsx`

### Rule ⑰+⑱ — 禁止空 catch + 统一错误展示
- `web/src/stores/app.ts` — 添加 `setError` action
- `web/src/components/ai/PipelineConfigPanel.tsx` — 修复 4 处空 catch，错误路由到 GlobalError

### Rule ⑬ (第二批—i18n)
- `web/src/components/dashboard/AIModelStatusCard.tsx`
- `web/src/components/dashboard/ContainerStatusCard.tsx`
- `web/src/components/dashboard/GPUStatusCard.tsx`
- `web/src/pages/Admin/Dashboard.tsx`
- `web/src/pages/Admin/ErrorDashboard.tsx`
- `web/src/pages/Admin/JobManagement.tsx`
- `web/src/pages/Admin/LogViewer.tsx`
- `web/src/i18n/locales/en.json` (新增 31 个 key)
- `web/src/i18n/locales/zh.json` (新增 31 个 key)


### Rule ⑬ (第四批—3 panel files)
- `web/src/components/ai/AIModuleConfigPanel.tsx`
- `web/src/components/ai/PipelineConfigPanel.tsx`
- `web/src/pages/DirectoryView.tsx`
- `web/src/i18n/locales/en.json` (新增 ~113 个 key)
- `web/src/i18n/locales/zh.json` (新增 ~113 个 key)

### Rule ⑬ (第三批—stores + format.ts i18n)
- `web/src/utils/format.ts`
- `web/src/stores/asset.ts`
- `web/src/stores/ai.ts`
- `web/src/stores/admin.ts`
- `web/src/stores/adminJobs.ts`
- `web/src/stores/library.ts`
- `web/src/stores/logs.ts`
- `web/src/stores/search.ts`
- `web/src/stores/grid.ts`
- `web/src/i18n/locales/en.json` (新增 17 个 key)
- `web/src/i18n/locales/zh.json` (新增 17 个 key)


### Rule ⑪
- `_vp_bak.tsx` / `_migrate_types.py` / `server/app/api/ai.py.bak2` / `.original` / `.refactor-backup` — 已删除
- `web/src/components/SearchResultCard.tsx` — 已删除
- `web/src/components/ai/AIStatsCards.tsx` — 已删除
- `web/_tmp_*.json` x7 — 已删除

### Rule ⑫
- `web/tsconfig.json` — `noUnusedLocals` / `noUnusedParameters` 开启
- `web/src/api/client.ts`
- `web/src/App.tsx`
- `web/src/components/ai/AIModuleConfigPanel.tsx`
- `web/src/components/ai/AISettings.tsx`
- `web/src/components/ai/BatchProgressSection.tsx`
- `web/src/components/ai/PipelineConfigPanel.tsx`
- `web/src/components/dashboard/ContainerStatusCard.tsx`
- `web/src/components/MetadataPanel.tsx`
- `web/src/components/Sidebar.tsx`
- `web/src/components/VideoPlayer.tsx`
- `web/src/pages/Admin/Dashboard.tsx`
- `web/src/pages/Admin/JobManagement.tsx`
- `web/src/pages/Admin/LogViewer.tsx`
- `web/src/pages/AssetGridFilters.tsx`
- `web/src/pages/AssetGridUtils.tsx`
- `web/src/pages/AssetGridVirtual.tsx`
- `web/src/pages/DirectoryView.tsx`
- `web/src/pages/LibraryManager.tsx`
- `web/src/pages/SearchPage.tsx`
- `web/src/pages/TagBrowse.tsx`
- `web/src/pages/TagManager.tsx`
- `web/src/stores/logs.ts`

---

## 执行约定（备忘）

1. **流程**：思考 → 方案 → 验证 → 确认 → 备份 → 修改 → 验证 → 删备份
2. **Store action 模式**：try/catch + re-throw，组件处理 loading 和 error
3. **备份命名**：.bak，验证通过即删除



---

## Search 性能优化 (2026-07-04)

**修改文件：** server/app/api/search.py

| # | 问题 | 修复 |
|---|---|---|
| 1 | _t0 在 if q: 内定义，post_clip 日志在外部引用 — q 为空时 NameError | 删除所有调试 timing 日志（5 行）|
| 2 | _t2 在 CLIP try 内定义，clip_process 日志在 try 外引用 — 异常时 NameError | 删除对应 timing 代码 |
| 3 | i_session.query() 同步阻塞事件循环 | 用 syncio.to_thread() 包裹 3 处查询 |
| 4 | cast(AIEngineJob.media_id, String).in_() 阻止 PG 索引 | 改用 UUID 对象直接比较，去掉 cast |

| 5 | 视频详情页画布过大 | VideoPlayer.tsx max-h 75vh→55vh |
