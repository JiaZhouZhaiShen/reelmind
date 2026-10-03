# ReelMind — AI-Powered Self-Hosted Video Library

[![CI](https://github.com/JiaZhouZhaiShen/reelmind/actions/workflows/ci.yml/badge.svg)](https://github.com/JiaZhouZhaiShen/reelmind/actions/workflows/ci.yml)

> A self-hosted video library manager for editors, teams, and AI agents. Inspired by IMMICH, **specialized for video**.

ReelMind manages thousands of video assets, auto-extracts scenes / subtitles / object tags / OCR / CLIP embeddings, and provides full-text + semantic hybrid search — with AI inference fully decoupled from the web API via a separate GPU container.

## Architecture (Docker Compose, 6 containers)

| Container | Port | GPU | Role |
|-----------|------|-----|------|
| `reelmind-server` | internal | — | FastAPI gateway, AI proxy, file scan, web backend |
| `reelmind-ai` | 2589 | ✅ | AI pipeline orchestration (5 models) |
| `reelmind-orchestrator` | — | — | Lightweight job scheduler |
| `reelmind-postgres` | — | — | Asset metadata + pgvector |
| `reelmind-redis` | — | — | Cache + progress pub-sub |
| `reelmind-nginx` | **2588** | — | Reverse proxy, zero-copy video streaming, static assets |

**AI pipeline (sequential):** TransNetV2 (scene cut) → YOLOv8n (objects) → PaddleOCR (text) → OpenCLIP (semantic vectors) → faster-whisper (transcript) (+ optional pyannote diarization).

## Screenshots

> Captured from a real local ReelMind instance. Thumbnails are blurred to protect private video content.

| Login page | Video library grid |
|---|---|
| ![Login](docs/images/login.png) | ![Video library grid](docs/images/library-grid.png) |

| Search results | Video player | AI engine |
|---|---|---|
| ![Search results](docs/images/search-results.png) | ![Video player](docs/images/video-player.png) | ![AI engine](docs/images/ai-engine.png) |

## Quick Start

No frontend build, no image build — prebuilt images are pulled from GHCR (frontend is baked into the images):

```bash
git clone https://github.com/JiaZhouZhaiShen/reelmind.git
cd reelmind

# 1. Configure environment (template is committed; placeholder only, no secrets)
cp .env.example .env
#    🔴 Edit .env: set strong DB_PASSWORD and JWT_SECRET (openssl rand -hex 32)

# 2. Pull and start
docker compose pull
docker compose up -d

# 3. Verify
curl http://localhost:2588/api/ping
# Open http://localhost:2588
```

**First user = admin:** the very first registered account gets the `admin` role automatically.

> GPU note: without an NVIDIA GPU, `reelmind-ai` still starts (AI features toggle off via `ENABLE_WHISPER` / `ENABLE_CLIP`) — the app works as a video manager / search tool. On GPU machines, enable CUDA with `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`.
> First AI run downloads models automatically into the data volume (whisper large-v3 ≈ 3GB+, tiny ≈ 1GB).
> Version pinning: set `REELMIND_VERSION` in `.env` (default `latest` tracks main; pin a release tag like `v9.26.1010` for production).

## Features

- **Video library management** — multi-library, NAS/external mounts, bulk scan & metadata extraction (ffprobe)
- **Search** — full-text, smart (metadata+tags+transcript), tag system, CLIP semantic similarity
- **Preview** — thumbnail grid, H.264 proxy streams, scene browser, web player with transcript overlay
- **AI (optional)** — scene detection, object tags, OCR, speech-to-text, speaker diarization
- **API** — full REST JSON API; health endpoints for external tooling / AI agents

## Configuration highlights

| Variable | Default | Notes |
|----------|---------|-------|
| `DB_PASSWORD` / `JWT_SECRET` | `change-me` | 🔴 must be replaced in production |
| `EXTERNAL_MEDIA_DIR` | `./media` | media library root (mount a NAS/share here) |
| `PORT_MAP` | `0.0.0.0:2588` | external port |
| `ENABLE_WHISPER` / `WHISPER_MODEL` | `false` / `tiny` | set `true` to enable; `large-v3` needs ~10GB RAM / GPU |
| `ENABLE_CLIP` | `false` | semantic search (~2GB extra RAM) |
| `REELMIND_VERSION` | `latest` | image tag; pin a release (e.g. `v9.26.1010`) in production |

Full list: see `.env.example` comments.

## Documentation

| Doc | Purpose |
|-----|---------|
| `docs/必读_项目介绍与部署指南.md` | Project intro + deployment guide (Chinese) |
| `docs/en/PROJECT_GUIDE.md` | Deployment guide (English mirror) |
| `docs/铁律.md` / `docs/en/IRON_RULES.md` | Development iron rules (34 rules, R0-R7) |
| `docs/规范/` / `docs/en/STANDARDS/` | Per-layer standards (ZH authoritative, EN mirror) |

## Development

Developers use the dev overlay (source bind mounts + local image builds):

```bash
# Build frontend (dev only — prod images already contain it)
cd web && npm install && npm run build

# Build images locally and start with source mounts
docker compose -f docker-compose.yml -f docker-compose.dev.yml build
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Backend (live reload via bind mount — restart container, no rebuild)
docker compose restart reelmind-server reelmind-ai reelmind-orchestrator

# Frontend hot reload
cd web && npm run dev   # http://localhost:5173 (proxies /api to :2588)

# Quality gates
./scripts/check.sh              # 13 iron-rule checks (also run by pre-commit)
cd web && npm run typecheck     # tsc --noEmit
```

## License

MIT © 2024 JiaZhouZhaiShen
