# REELMIND Iron Rules

> English translation. The Chinese file `docs/铁律.md` remains the authoritative source.
> This document states principles and boundaries only; guidance takes priority.
> Each rule = ID + one-sentence principle. Execution details live in `docs/规范/` (Chinese) and the English mirrors under `docs/en/STANDARDS/`; machine checks live in `scripts/check.sh`.
> Do not look here for answers to specific bugs/optimizations/refactors. Follow the workflow in standard 00 to produce a proposal first.
> Changing this document requires syncing the related standard + script + `docs/铁律修订记录.md` (four-step closure).

---

## 0. Workflow Rules (Overview)

> Think -> Plan -> Verify -> Confirm -> Backup -> Change -> Verify -> Remove backup

| ID | Rule | Standard | Script |
|----|------|----------|--------|
| R0.1 | Verify before acting: read the baseline before changes; reproduce bugs, confirm behavior changes, and confirm refactor logic first. Changing without verification means owning the breakage | 00 | - |
| R0.2 | Plan before code: produce a plan, verify and confirm it, then back up and change. Major changes require confirmation before touching code | 00 | - |
| R0.3 | Backup rule: back up any file to `backups/{timestamp}_{description}/` before modifying it; delete the backup only after verification passes | 00 | backup.sh |
| R0.4 | Minimal change: do only what the task requires; do not fix unrelated bugs, refactor, or expand scope. Surface problems, but do not fix them unilaterally | 00 | - |
| R0.5 | Plans need boundaries: every plan must state scope (what to do / what not to do / files involved / acceptance criteria); execute strictly inside the boundary and re-confirm before expanding it | 00 | - |
| R0.6 | Common quality standard: naming, commits, formatting, and documentation maintenance follow `docs/规范/06_质量规范.md` (English: 06_QUALITY.md) across all layers | 06 | - |

## 1. Backend Rules

| ID | Rule | Standard | Script |
|----|------|----------|--------|
| R1.1 | Server forwards only, never computes AI: it loads no AI models and does no GPU inference; all AI requests are HTTP-proxied to the AI container | 01 | check.sh |
| R1.2 | Two databases, one job each: state/metadata -> PG; AI inference results -> SQLite; vectors -> PG (pgvector). No data is dual-written | 01 | - |
| R1.3 | Single status write entry: each container has exactly one write module (Server = `app/core/job_helpers.py`, AI = `ai_service/job_helpers.py`); all other code is forbidden from writing `ai_engine_jobs` / `processing_state` directly | 01 | check.sh |
| R1.4 | Single-responsibility APIs: `api` files stay <= 1000 lines; responsibility matters more than line count; split when over the limit | 01 | check.sh |
| R1.5 | Backend does no rendering math: percentages and formatting belong to the frontend; business aggregation/state derivation may stay backend-side | 01 | - |

## 2. Frontend Rules

| ID | Rule | Standard | Script |
|----|------|----------|--------|
| R2.1 | Business state lives in stores: API data must go into Zustand stores; component `useState` is only for UI state | 02 | - |
| R2.2 | Children read from stores: do not drill business props through parents (warning above 5 business props) | 02 | - |
| R2.3 | Components self-handle three states: every component manages its own loading/error/empty states instead of relying on its parent | 02 | - |
| R2.4 | Page-level ErrorBoundary: every routed page must be wrapped in an ErrorBoundary | 02 | - |
| R2.5 | Memoize hot components: list items/cards/sidebars use `React.memo`; a project with zero memo is a performance bug | 02 | check.sh |
| R2.6 | No empty catches: every catch must give user-visible feedback (exceptions: `video.play`, clipboard, SSE parsing) | 02 | check.sh |
| R2.7 | No hard-coded Chinese in i18n: all user-visible text goes through `t('key')` | 02 | check.sh |
| R2.8 | No dead-code leftovers: source trees forbid `.bak` / `.refactor-backup` / `.original` / zero-reference pages | 02 | check.sh |
| R2.9 | Strict TypeScript: `strict` + `noUnusedLocals` + `noUnusedParameters` must be enabled | 02 | check.sh |
| R2.10 | Page components <= 1000 lines: split into sub-components beyond that (applies to both `pages/` and `components/`) | 02 | check.sh |

## 3. API Rules

| ID | Rule | Standard | Script |
|----|------|----------|--------|
| R3.1 | Split APIs by domain: `api/` is organized by business domain; `client.ts` is a barrel export only (<= 50 lines) | 03 | check.sh |
| R3.2 | Unified error display: API errors go into a store and are rendered by the page-level `GlobalError` component | 03 | - |

## 4. Scheduling Rules

| ID | Rule | Standard | Script |
|----|------|----------|--------|
| R4.1 | Separate status from results: `ai_engine_jobs.status` -> PG; scenes/subtitles/tags/OCR -> SQLite | 04 | - |
| R4.2 | Display depends on results_ready: the frontend never reads engine status directly; it always consumes the backend `results-ready` endpoint, and the backend owns and documents how results_ready is derived | 04 | - |

## 5. Container Rules

| ID | Rule | Standard | Script |
|----|------|----------|--------|
| R5.1 | AI/Orchestrator must be stateless: deleting and recreating a container must not affect data; model weights are pre-baked into the image | 05 | - |
| R5.2 | No docker.sock mounts: no container may mount `/var/run/docker.sock` | 05 | check.sh |
| R5.3 | Cross-container traceability: cross-container requests propagate `trace_id`; logs are structured and written to stdout | 05 | - |

## 6. Data Rules

| ID | Rule | Standard | Script |
|----|------|----------|--------|
| R6.1 | Model changes go through migrations: changing SQLAlchemy models requires generating and running an alembic migration; manual ALTER/CREATE TABLE is forbidden | 07 | check.sh |
| R6.2 | Back up data before touching it: any database write (migration/cleanup/import) requires backing up the database first (pg_dump for PG, copy `.db` for SQLite), same level as R0.3 | 07 | backup.sh |
| R6.3 | Deletion closes the loop: deleting an asset must clean up related results (scenes/subtitles/tags/vectors/job records); orphaned data is forbidden | 07 | - |

## 7. Engineering Process Rules

| ID | Rule | Standard | Script |
|----|------|----------|--------|
| R7.1 | Dependency changes require rebuilds: after changing requirements.txt / package.json you must rebuild the image and verify; changing files alone is not enough | 08 | - |
| R7.2 | Config changes require verification: after changing .env / config.py you must restart containers and verify it took effect; .env must never be committed | 08 | check.sh |
| R7.3 | New modules must be registered: new containers/services/engines must update docker-compose and the documentation index | 08 | - |

---

## Document Index

| Document | Path |
|----------|------|
| Workflow standard | `docs/规范/00_工作流程.md` (EN: `docs/en/STANDARDS/00_WORKFLOW.md`) |
| Backend standard | `docs/规范/01_后端规范.md` (EN: `docs/en/STANDARDS/01_BACKEND.md`) |
| Frontend standard | `docs/规范/02_前端规范.md` (EN: `docs/en/STANDARDS/02_FRONTEND.md`) |
| API standard | `docs/规范/03_API规范.md` (EN: `docs/en/STANDARDS/03_API.md`) |
| Scheduling standard | `docs/规范/04_调度规范.md` (EN: `docs/en/STANDARDS/04_SCHEDULING.md`) |
| Container standard | `docs/规范/05_容器规范.md` (EN: `docs/en/STANDARDS/05_CONTAINER.md`) |
| Quality standard | `docs/规范/06_质量规范.md` (EN: `docs/en/STANDARDS/06_QUALITY.md`) |
| Data standard | `docs/规范/07_数据规范.md` (EN: `docs/en/STANDARDS/07_DATA.md`) |
| Engineering standard | `docs/规范/08_工程流程规范.md` (EN: `docs/en/STANDARDS/08_ENGINEERING.md`) |
| Iron rule revision log | `docs/铁律修订记录.md` |
| Hard-rule check script | `scripts/check.sh` |
| Unified backup script | `scripts/backup.sh` |
| CLAUDE.md (entry point) | `CLAUDE.md` |
| CODEX.md (Codex execution constraints) | `CODEX.md` |
