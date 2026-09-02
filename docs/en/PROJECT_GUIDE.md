# ReelMind: Project Introduction and Deployment Guide

> Version: 2026-09-02
> English translation. The Chinese file `docs/必读_项目介绍与部署指南.md` is authoritative.
> Positioning: a self-hosted AI video library manager built for editing teams, creators, and AI agents, focused on video (the counterpart to what Immich is for photos).
> This guide was written against the actual repository configuration; all commands were verified against `docker-compose.yml`, `.env.example`, and `CLAUDE.md`.

---

## 1. What ReelMind Is

**ReelMind** is a self-hosted video asset library manager. It manages thousands of video assets and automatically extracts scenes, subtitles, object tags, OCR text, and CLIP semantic vectors, offering hybrid retrieval that combines full-text search with semantic search.

Core design: the **AI inference pipeline is fully decoupled from the Web API**. The Web service loads no AI models; AI computation runs in a separate GPU container and is reached through an HTTP proxy, so the Web API stays responsive while AI is busy.

### System Architecture (6 containers + 1 network)

| Container | Port | GPU | Image | Role |
|-----------|------|-----|-------|------|
| `reelmind-server` | internal (behind nginx) | no | `server/Dockerfile.slim` | FastAPI gateway, AI proxy, file scanner, web backend, static files |
| `reelmind-ai` | 2589 | yes | `server/ai_service/Dockerfile` | AI pipeline orchestration (5 models), separate image and VRAM |
| `reelmind-orchestrator` | - | no | `server/orchestrator/Dockerfile` | lightweight job scheduler (replaces Celery Beat) |
| `reelmind-postgres` | - | - | `pgvector/pgvector:pg16` | asset metadata + pgvector vector index |
| `reelmind-redis` | - | - | `redis:7-alpine` | cache, queues, progress pub-sub |
| `reelmind-nginx` | **2588** (public) | no | `nginx/Dockerfile` | reverse proxy, zero-copy video delivery, static assets |

Data flow:

```
Client -> nginx(2588) -> reelmind-server
  |-- non-AI requests -> PostgreSQL / SQLite / filesystem
  `-- /api/ai/* -> HTTP proxy -> reelmind-ai(2589) -> results written to shared SQLite
Orchestrator: polls PG -> schedules AI jobs -> updates ai_engine_jobs
```

Storage convention (two databases, separate jobs):
- **PostgreSQL**: asset metadata, pipeline state (`ai_engine_jobs`), pgvector vectors
- **SQLite** (`data/reelmind/reelmind_ai.db` and others): AI inference results (scenes/subtitles/tags/OCR)
- Status drives scheduling, results drive display; the two are never mixed

---

## 2. Main Features

### Video Library Management
- Multi-library organization: create multiple video libraries and manage thousands of assets by category
- External library mounts: reference local disks / NAS / network shares directly (read-only mounts, no copying)
- Batch import and scanning: auto-discover new files and index them
- Metadata extraction: ffprobe reads codec / resolution / fps / duration / bitrate / audio track info

### Retrieval
- Full-text search: file names, notes, subtitle text
- Smart search: combined metadata + tags + subtitle content
- Tag system: manual tags + AI auto-tags with category management
- **Semantic search**: CLIP vector similarity (requires AI enabled)

### Preview and Playback
- Thumbnail grid: automatic thumbnails for every video
- Proxy video: lightweight H.264 proxy streams for smooth web playback (bitrate/width configurable)
- Scene browser: auto-split scene segments with per-scene thumbnails
- In-browser player with subtitle timeline overlay

### AI Pipeline (optional)

| Model | Purpose | Weights |
|-------|---------|---------|
| TransNetV2 | scene cuts | - |
| YOLOv8n | object detection / auto tags | 8.3.0 |
| PaddleOCR | on-screen text recognition | 2.8.0 |
| OpenCLIP | semantic vectors (similarity search) | ViT-B-16 |
| faster-whisper | speech to text | large-v3 / tiny etc. |

The pipeline runs in order: scene cut -> object detection -> OCR -> CLIP vectors -> speech transcription (+ optional speaker diarization).

### API and Integration
- REST API: full JSON interfaces for external tools and AI agents
- Async jobs: Orchestrator schedules the pipeline
- Health checks: `/api/ping`, `/health`, system status panel

---

## 3. What It Can Do for You

1. An AI brain for your editing footage library: find footage by content (subtitles, objects, scenes, semantic similarity), not by memory.
2. Automatic per-asset AI annotation: after scanning, scenes, OCR, transcription, and object tags are produced automatically.
3. Hybrid retrieval in practice: search a video by file name, by "what was said", by "what appears in the frame", or by semantic similarity.
4. Collaborative web browsing: teams browse, search, and preview in the browser; nginx zero-copy delivery keeps resource load low.
5. Open to AI agents: the REST API lets agents search and trigger tasks, evolving toward an "AI workbench".

---

## 4. Dependency Checklist

> Dependencies come in three layers: host system (required outside containers), image-bundled (installed by Dockerfiles; deployers just need to know), and runtime models (auto-downloaded on first run).

### 4.1 Host Dependencies (install before redeploying)

| Dependency | Version | Purpose | Required |
|------------|---------|---------|----------|
| Docker Engine + Compose v2 | 20.10+ / compose v2 | container orchestration | YES |
| NVIDIA driver + `nvidia-container-toolkit` | CUDA 12.4 support | GPU acceleration for the AI container (`runtime: nvidia`) | YES when using AI |
| `openssl` | any | generate `JWT_SECRET` | recommended |
| Disk space | 50GB+ for data directory | PG + SQLite + media + model cache | YES |
| `ffmpeg` / `ffprobe` | see 4.2 | local development only (bundled inside containers) | optional |

### 4.2 Image-Bundled Dependencies (declared in Dockerfiles, no manual install)

All container bases: Linux + Python 3.12 (ai/orchestrator) + Python slim (server)

| Container | System packages (apt) | Python deps source |
|-----------|----------------------|--------------------|
| `reelmind-server` | `ffmpeg curl tini` | `server/requirements.txt` |
| `reelmind-ai` | `python3.12 ffmpeg curl tini` (deadsnakes PPA) | `server/ai_service/requirements.txt` |
| `reelmind-orchestrator` | none extra | `server/orchestrator/requirements.txt` |
| `reelmind-postgres` | from image | - (`pgvector/pgvector:pg16`) |
| `reelmind-redis` | from image | - (`redis:7-alpine`) |

Key Python dependencies (three requirements files, verified):

- **server** (web gateway): `fastapi / uvicorn / sqlalchemy / asyncpg / psycopg2-binary / alembic / pgvector / redis / pydantic / python-multipart / ffmpeg-python / opencv-python-headless / httpx / passlib+bcrypt / python-jose` and more
- **ai_service** (GPU inference): `torch 2.5.1 + torchvision + torchaudio`, `transnetv2-pytorch`, `ultralytics 8.3.0`, `paddleocr 2.8.0 + paddlepaddle 3.3.1`, `open-clip-torch 2.29.0`, `faster-whisper 1.1.1`, `pyannote.audio 3.1.1`, `scenedetect 0.6.2` and more
- **orchestrator**: lightweight scheduling deps (`server/orchestrator/requirements.txt`)

### 4.3 Frontend Dependencies (for building web/dist)

Core packages in `web/package.json` (verified): `react 18.3.x`, `react-dom`, `zustand 4.5.2`, `vite 5.3.x`, `i18next 26.x`, `typescript 5.4.x`. Install with `npm install` (Node.js must satisfy Vite; Node 18+/20+ recommended).

### 4.4 Runtime Models (auto-downloaded into the data volume on first run)

The AI container downloads models to `/data/reelmind/models` (mounted volume) on first pipeline run; downloads require network access:

| Model | Approx size | Feature |
|-------|-------------|---------|
| faster-whisper `large-v3` | ~3GB+ | transcription (`WHISPER_MODEL=tiny` to save resources) |
| open-clip `ViT-B-16` | ~350MB | semantic vectors |
| PaddleOCR | tens of MB | on-screen text |
| YOLOv8n | ~6MB | object tags |
| pyannote diarization | hundreds of MB | speaker diarization (requires `HUGGINGFACE_TOKEN`) |

If model downloads fail: check the `data/reelmind/models` volume, disk space, and network; HF models require access to huggingface.co.

---

## 5. Redeploy Steps

Prerequisites: Docker + Docker Compose v2; NVIDIA GPU + nvidia-container-runtime (for the AI container; remove `runtime: nvidia` temporarily if you do not use AI).

### Step 1: Prepare the project directory and config

```bash
# Enter the project root (the directory containing docker-compose.yml)
cd reelmind

# Create .env from the template if it does not exist
cp .env.example .env
```

Notes when deploying from a GitHub clone:

| Item | Notes |
|------|-------|
| `.env.example` is committed | The template contains `change-me` placeholders, no real secrets; copy it directly after clone |
| **Images: GHCR optional, local build by default** | Self-built images are published to `ghcr.io/jiazhouzhaishen/*` (Public); without `REELMIND_*_IMAGE` vars you still run `docker compose build`; with them, run `docker compose pull` (see README). postgres / redis use official images |
| **Node version** | Frontend builds need Node.js >= 18 (Vite 5), 20 LTS recommended; no `.nvmrc` yet |
| `media/` samples are not committed | Create `media/` or mount an external directory after clone (see `EXTERNAL_MEDIA_DIR` in `.env`) |
| `data/` is not committed | PG/SQLite/model cache are generated at runtime; an empty `data/` after clone is normal |
| Model weights are not committed | AI models auto-download into the data volume on first run (see 4.4) |

### Step 2: Edit `.env` (key items)

| Item | Must change | Notes |
|------|-------------|-------|
| `DB_PASSWORD` | YES | replace with a strong password in production |
| `JWT_SECRET` | YES | generate: `openssl rand -hex 32` |
| `EXTERNAL_MEDIA_DIR` | as needed | media directory (NAS example `/volume1/video/footage`) |
| `REELMIND_DATA_ROOT` | as needed | data directory (default `./data/reelmind`) |
| `PGDATA_ROOT` | as needed | PG data directory (default `./data/postgres`) |
| `PORT_MAP` | as needed | public port (default `0.0.0.0:2588`) |
| `ENABLE_WHISPER` / `WHISPER_MODEL` | as needed | transcription; `tiny` on NAS, `large-v3` with VRAM |
| `ENABLE_CLIP` | as needed | semantic vectors (~+2GB memory) |
| `HUGGINGFACE_TOKEN` | when diarization is enabled | required for speaker separation |
| `AI_MEM_LIMIT` / per-service `MEM_LIMIT` | as needed | lower for low-memory devices (NAS 4GB reference in `.env.example` comments) |

### Step 3: Build the frontend (web/dist is mounted read-only)

```bash
cd web
npm install        # first time
npm run build      # outputs to web/dist/
cd ..
```

Note: `web/dist` is mounted into containers as `:ro`. You must build before starting containers, otherwise pages 404.

### Step 4: Build images and start

```bash
# Build all images (slow the first time, includes model download environments)
docker compose build

# Start
docker compose up -d
```

> To deploy from GHCR without a local build: set the four `REELMIND_*_IMAGE` variables (default `latest`; pin a release tag once published, e.g. `REELMIND_SERVER_IMAGE=ghcr.io/jiazhouzhaishen/reelmind-server:latest`), then run `docker compose pull && docker compose up -d`. The frontend `web/dist` still needs one local build in v1 (see README).

### Step 5: Verify health

```bash
# 1. Container status
docker compose ps          # all containers should be Up (healthy)

# 2. Web / API
curl http://localhost:2588/api/ping

# 3. AI service
curl http://localhost:2589/health

# 4. Open the browser
# http://localhost:2588
```

### Step 6: First-use flow

1. Open the Web UI in a browser.
2. **First login (important)**: click register and create the first account. The first registered user automatically receives the admin role (see `auth.py`; there is no preset account; `username` >= 2 chars, `password` >= 6 chars).
3. Log in with that admin account and create a library.
4. Point settings at the media directory (`.env` `EXTERNAL_MEDIA_DIR`).
5. Trigger "scan media library" - the server indexes asset metadata.
6. Optional: trigger the AI pipeline (single video / batch) - the AI container runs the 5 models and writes results to SQLite.
7. Try full-text / semantic search on the search page.

### Step 7 (optional): Database migrations

```bash
# The container runs alembic upgrade head automatically at startup after upgrades
# Manual execution:
docker compose exec reelmind-server alembic upgrade head
```

---

## 6. Deployment Notes

### 1. Security (must read)
- **Default passwords are unsafe**: `change-me` / `reelmind` values in compose are dev defaults. In production change `DB_PASSWORD`, `JWT_SECRET`, and `HUGGINGFACE_TOKEN`.
- **Never commit `.env`**: `.gitignore` excludes it; never `git add -f .env`.
- **No docker.sock mount**: removed, eliminating container-escape risk.
- Use HTTPS for any public exposure (a front reverse proxy is recommended).

### 2. Frontend build order (easiest pitfall)
`web/dist` is mounted read-only into nginx and the server. After changing frontend code you must re-run `npm run build`. Running only `vite dev` affects local port 5173 and does not change in-container pages.

### 3. Code hot reload (development mode)
`server/`, `server/ai_service/`, and `server/orchestrator/` are bind-mounted into containers. In development, Python code changes require no image rebuild; restart the container:
```bash
docker compose restart reelmind-server reelmind-ai reelmind-orchestrator
```
If you changed `requirements.txt` / `package.json`, rebuild the image: `docker compose build <service>`.

### 4. GPU and AI
- The AI container uses `runtime: nvidia`; the host needs NVIDIA driver + nvidia-container-toolkit; without a GPU the container fails to start.
- Models auto-download to `/data/reelmind/models` (mounted volume); they are large (whisper large-v3 ~3GB+), so the first start is slow by design.
- Low-memory devices: `WHISPER_MODEL=tiny`, `ENABLE_CLIP=false`.

### 5. Data and backups
- Data lives in three places: PG (`PGDATA_ROOT`), SQLite + media (`REELMIND_DATA_ROOT`), Redis (`REDIS_DATA_ROOT`).
- Back up the database with `scripts/backup.sh`: `./scripts/backup.sh <description> --db` (PG pg_dump + SQLite copy).
- Back up before deleting assets; back up before any migration/cleanup (iron rule R6.2).

### 6. Common troubleshooting

| Symptom | Investigation |
|---------|---------------|
| Blank frontend / pages 404 | Was `web/dist` built? Run `npm run build`, then start containers |
| `/api/ping` works but page 500s | `docker logs reelmind-server` and check the traceback |
| AI stuck | `docker logs reelmind-ai`; inspect `ai_engine_jobs` status |
| Models keep downloading | Check `data/reelmind/models` volume and disk space |
| Port in use | Change `PORT_MAP` in `.env`, then `docker compose up -d` |
| Database unreachable | `docker compose logs postgres`; check `DB_*` in `.env` |

### 7. Health self-check (run after deployment)

```bash
# Iron-rule hard checks (repo script, 13 items)
./scripts/check.sh

# Three probes
docker compose ps
curl http://localhost:2588/api/ping
curl http://localhost:2589/health
```

---

## 7. Related Documents

| Document | Purpose |
|----------|---------|
| `docs/铁律.md` | Iron rules (34 items, R0-R7) |
| `docs/规范/00-08` | Layer execution standards |
| `docs/必读_NEW_ENGINEER_ONBOARDING.md` | 5-day onboarding |
| `docs/安全审计报告_2026-07-30.md` | security hardening record |
| `docs/_archive/` | archived historical docs |
