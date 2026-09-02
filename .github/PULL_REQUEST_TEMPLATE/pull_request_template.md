# Pull Request

## 描述 / Description

<!-- 本次改动做了什么 / What this PR does -->

## 边界 / Scope

- **做什么**：
- **不做什么**：
- **涉及文件**：

## 铁律自查 / Iron-rule self-check (all must pass)

- [ ] `./scripts/check.sh` — 13 项硬规则 0 违规（新增违规拦截）
- [ ] `cd web && npm run typecheck` — 0 错误
- [ ] `cd web && npm run build` — 通过（若涉及前端）
- [ ] 无 `.env` / `.bak` / `backups/` 入库
- [ ] 涉及 `ai_engine_jobs` → 走 job_helpers 写入口（R1.3）
- [ ] 涉及数据库 → 走 alembic 迁移（R6.1）
- [ ] 涉及依赖 → 已重建镜像验证（R7.1）
- [ ] 涉及配置 → 已重启验证生效（R7.2）
- [ ] 文档已同步（新增模块/规则变更更新 docs）

## 验收 / Verification

- [ ] 功能符合预期（bug 修复不复现 / 新功能按设计工作）
- [ ] 回归无破坏（后端改动 → 前端页面正常；前端改动 → 无 500）

<!-- 关联 issue / Closes # -->
