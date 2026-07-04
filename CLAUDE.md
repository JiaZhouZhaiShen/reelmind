# REELMIND Project Context

> ⚠️ AI 执行铁律：先思考，再出方案，方案经验证后确认，确认后备份再修改，修改后验证，验证完删备份。
>
> 在修改任何文件之前，必须先 Read 文件确认当前内容，了解改动基线。
> 修 bug 先复现、改行为先确认当前行为、重构先确认现有逻辑。
> 不验证就改 → 改坏了不负责。

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
│   ├── app/              # FastAPI app (~14K lines)
│   │   ├── api/          # Routes (assets.py 1104, admin.py 771)
│   │   ├── core/         # indexer.py 1217, job_helpers.py
│   │   ├── models/       # SQLAlchemy ORM
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Business logic
│   │   ├── main.py       # FastAPI entry
│   │   ├── config.py     # Pydantic settings
│   │   └── database.py   # Session management
│   ├── ai_service/       # GPU AI container (~3.5K lines)
│   │   ├── main.py       # AI FastAPI entry (818 lines)
│   │   ├── pipeline.py   # Core pipeline engine (897 lines)
│   │   ├── services/     # Per-engine services (scene/yolo/ocr/clip/whisper/diarization)
│   │   └── configs/      # Per-engine config modules
│   ├── orchestrator/     # Job scheduler (~550 lines)
│   └── alembic/          # DB migrations (0001-0006)
├── web/
│   └── src/
│       ├── pages/        # Page components (~7K lines)
│       ├── components/   # Reusable (~4.3K lines)
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

## Key Architecture Rules (see 铁律文档 for full 25 rules)

- Server never loads AI models — all AI via HTTP proxy
- Business state → Zustand store, not component useState
- Child components read from store, not parent props
- Every component handles loading/error/empty states
- Every page wrapped in ErrorBoundary
- No empty catch(() => {})
- DB: ai_engine_jobs via job_helpers, not direct SQL
- State in PG, results in SQLite
- No docker.sock mount
- Frontend: no .bak files, React.memo for list items, i18n not hardcoded Chinese

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

# Start AI pipeline (test)
curl -X POST http://localhost:2589/pipeline/start -H "Content-Type: application/json" -d '{"limit":5}'
```
