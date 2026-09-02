# REELMIND Project Context

> ⚠️ AI 执行铁律总纲：思考 → 方案 → 验证 → 确认 → 备份 → 修改 → 验证 → 删备份
> 不验证就改 → 改坏了不负责。改前先备份到 `backups/{时间戳}_{描述}/`，备份完成前不允许修改。
> 只做任务范围内的事，不顺手改别的。发现的问题可以提出，不能擅自改。

## 铁律速查（完整版见 docs/铁律.md，细则见 docs/规范/，硬规则自查 ./scripts/check.sh）

- **工作流程**：R0.1 先验证再动手 / R0.2 先方案后代码 / R0.3 备份铁律 / R0.4 最小改动 / R0.5 方案必有边界 / R0.6 质量通用标准
- **后端**：R1.1 Server 无 AI 推理 / R1.2 双库分离不双写 / R1.3 状态唯一入口每容器一模块(Server=core/job_helpers.py, AI=ai_service/job_helpers.py) / R1.4 接口≤1000行 / R1.5 不做渲染计算
- **前端**：R2.1 状态归 store / R2.2 子组件读 store / R2.3 三态自包含 / R2.4 ErrorBoundary / R2.5 高频组件 memo / R2.6 禁空 catch / R2.7 i18n 无硬编码中文 / R2.8 无.bak死代码 / R2.9 TS严格 / R2.10 页面≤1000行
- **API**：R3.1 按域拆分(client.ts≤50行,已入check.sh) / R3.2 统一错误展示
- **调度**：R4.1 状态PG结果SQLite / R4.2 展示看 results_ready
- **容器**：R5.1 AI/Orchestrator stateless / R5.2 禁 docker.sock / R5.3 trace_id 追踪
- **数据**：R6.1 模型变更走迁移 / R6.2 数据先备份后动 / R6.3 删除走闭环
- **工程**：R7.1 依赖变更必重建 / R7.2 配置变更必验证 / R7.3 新增模块必注册

## 动手前 3 秒自查

```bash
docker compose ps
curl http://localhost:2588/api/ping
curl http://localhost:2589/health
```

改动后必跑 `./scripts/check.sh` 确认无违规。

## What is ReelMind?

Self-hosted video library manager for editing teams. Manages thousands of video assets, auto-extracts scenes/subtitles/object-tags/OCR/CLIP embeddings, provides full-text + semantic hybrid search.

## Architecture (5 containers)

| Container | Port | GPU | Role |
|-----------|------|-----|------|
| reelmind-server | 2588 | no | FastAPI gateway, AI proxy, file scan, web backend |
| reelmind-ai | 2589 | yes | AI pipeline orchestration (5 models) |
| reelmind-orchestrator | — | no | Lightweight job scheduler (replaced Celery Beat) |
| reelmind-postgres | — | — | Asset metadata + pgvector |
| reelmind-redis | — | — | Cache + progress pub-sub |

## Data flow

```
Web UI → REST/SSE → reelmind-server
  ├── Non-AI → PG / SQLite / filesystem
  └── /api/ai/* → HTTP proxy → reelmind-ai (2589)
       └── results → SQLite (shared volume) → server reads

Orchestrator: polls PG → schedules AI engine jobs → updates ai_engine_jobs
```

## Key directories

```
D:\DockerData\reelmind/
├── server/
│   ├── app/              # FastAPI app
│   │   ├── api/          # Routes
│   │   ├── core/         # indexer.py, job_helpers.py
│   │   ├── models/       # SQLAlchemy ORM
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Business logic
│   │   ├── main.py       # FastAPI entry
│   │   ├── config.py     # Pydantic settings
│   │   └── database.py   # Session management
│   ├── ai_service/       # GPU AI container
│   │   ├── main.py       # AI FastAPI entry
│   │   ├── pipeline.py   # Core pipeline engine
│   │   ├── services/     # Per-engine services (scene/yolo/ocr/clip/whisper/diarization)
│   │   └── configs/      # Per-engine config modules
│   ├── orchestrator/     # Job scheduler
│   └── alembic/          # DB migrations
├── web/
│   └── src/
│       ├── pages/        # Page components
│       ├── components/   # Reusable
│       ├── api/          # API client layer
│       ├── stores/       # Zustand stores
│       ├── i18n/         # en/zh
│       └── types/        # TypeScript types
├── docker-compose.yml
└── .env.example
```

## AI Pipeline (order: 5 models, sequential)

1. TransNetV2 — scene cut
2. YOLOv8n — object detection
3. PaddleOCR — text recognition
4. OpenCLIP — semantic embedding
5. faster-whisper — speech-to-text (+ optional pyannote diarization)

Modes: Single (specified video_ids) / Batch (pending videos from PG)

## 关键文档索引

| 文档 | 用途 |
|------|------|
| `docs/铁律.md` | 铁律本体（R0-R7 全部 34 条） |
| `docs/规范/00-08` | 各层执行细则 |
| `docs/铁律修订记录.md` | 铁律变更闭环记录 |
| `docs/必读_README.md` | 项目定位与快速启动 |
| `docs/必读_NEW_ENGINEER_ONBOARDING.md` | 新人 5 天上手 |
| `CODEX.md` | Codex 执行约束 |

## Common Commands

```bash
# Start everything
docker compose up -d

# Frontend dev
cd web && npx vite --host 127.0.0.1 --port 5173

# Frontend build
cd web && npm run build

# Rebuild single service
docker compose build reelmind-server

# View logs
docker logs -f reelmind-ai
docker logs -f reelmind-server

# DB migration
docker compose exec reelmind-server alembic upgrade head

# Enter DB
docker compose exec postgres psql -U reelmind

# Check AI health
curl http://localhost:2589/health

# 铁律硬规则自查
./scripts/check.sh
```
