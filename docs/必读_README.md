# ReelMind — AI-Powered Video Library Management

> A self-hosted video library manager built for editors, teams, and AI agents.  
> Inspired by IMMICH, **specialized for video**.

![ReelMind](docs/assets/hero.png)

## Features

### Core
- **Video Library Management** — Organize thousands of video assets across multiple libraries
- **External Library Mounting** — Reference files on local drives, NAS, or network shares
- **Bulk Import & Scanning** — Automatic discovery and indexing of new files
- **Metadata Extraction** — Codec, resolution, FPS, duration, bitrate, audio info via ffprobe

### Search
- **Full-Text Search** — Search filenames, notes, and transcripts
- **Smart Search** — Multi-dimensional search combining metadata, tags, and transcript content
- **Tag System** — Manual + AI-generated tags with categories

### Preview & Playback
- **Thumbnail Grid** — Auto-generated thumbnails for each video
- **Proxy Videos** — Lightweight H.264 proxies for smooth web playback
- **Scene Browser** — Auto-detected scene segments with per-scene thumbnails
- **Web Player** — Browser-based video player with seek and transcript overlay

### AI (Optional)
- **Speech-to-Text** — Whisper-powered transcription with timestamp alignment
- **Visual Embeddings** — CLIP-based semantic similarity search
- **Scene Detection** — Automatic content-aware scene segmentation

### API & Extensibility
- **REST API** — Full-featured JSON API for external tools and AI agents
- **Async Jobs** — Orchestrator-based job scheduling
- **Webhooks** — Event notifications for integrations (planned)

## Quick Start

### Prerequisites
- Docker & Docker Compose
- FFmpeg (for local development)

### Using Docker Compose

```bash
# Clone and enter the directory
git clone https://github.com/your/reelmind.git
cd reelmind

# Start all services
docker compose up -d

# Open the web UI
open http://localhost:2588
```

### Local Development

```bash
# Backend
cd server
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --reload --port 2588

# Frontend
cd web
pnpm install
pnpm run dev
```

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_*` | localhost | PostgreSQL connection |
| `REDIS_*` | localhost | Redis connection |
| `DATA_ROOT` | ~/.reelmind | Storage root |
| `PORT` | 2588 | Server port |
| `ENABLE_WHISPER` | false | Enable speech-to-text |
| `ENABLE_CLIP` | false | Enable visual embeddings |
| `ENABLE_FACE_DETECT` | false | Enable face detection |

## API

Full API documentation available via server endpoints.  
Key endpoints:

- `GET /api/ping` — Health check
- `POST /api/libraries` — Create library
- `GET /api/assets` — List assets
- `GET /api/search/smart?q=query` — Smart search
- `GET /api/preview/thumbnail/{id}` — Get thumbnail
- `GET /api/preview/proxy/{id}` — Stream proxy video

## Roadmap

- [x] Core data model and API
- [x] Video scanning and metadata extraction
- [x] Thumbnail and proxy generation
- [x] Scene detection
- [x] Smart search (metadata + transcript)
- [x] Docker Compose deployment
- [ ] Authentication and multi-user support
- [ ] Webhook system
- [ ] AI agent API (MCP integration)
- [ ] Advanced clip editing and timeline
- [ ] S3-compatible storage backend
- [ ] Real-time collaboration

## License

MIT

---

## Architecture

```
Web UI (React) ↔ FastAPI REST API (reelmind-server)
                                  ↔ PostgreSQL (pgvector)
                                  ↔ Redis (cache + progress pub-sub)
                                  ↔ reelmind-orchestrator (job scheduler)
                                  ↔ reelmind-ai (GPU AI pipeline via HTTP)
```

### 容器拆分

AI 推理管线从主 API 服务器分离为独立容器 `reelmind-ai`，自有 GPU 资源和独立镜像。

| 容器 | 镜像 | GPU | 职责 |
|------|------|-----|------|
| `reelmind-server` | `server/Dockerfile.slim` | ❌ | API HTTP 代理、scan-library、auto-run 调度 |
| **`reelmind-orchestrator`** | **`server/orchestrator/Dockerfile`** | **❌** | **轻量作业调度器（替代 Celery Beat）** |
| **`reelmind-ai`** | **`server/ai_service/Dockerfile`** | **✅** | **管线编排 + 5 个 AI 模型** |
| `reelmind-postgres` | pgvector/pg16 | — | 主数据库（资产元数据 + pgvector） |
| `reelmind-redis` | redis:7-alpine | — | 缓存、队列、进度推送 |

### AI 依赖清单

| 模型 | 库 | 版本 |
|------|----|------|
| 框架 | PyTorch | 2.5.1 (CUDA 12.4) |
| 语音转文字 | faster-whisper | large-v3 |
| 语义视觉搜索 | open-clip | ViT-B-16 |
| 场景切割 | TransNetV2 | — |
| 物体检测 / 自动标签 | YOLOv8n (ultralytics) | 8.3.0 |
| 画面文字识别 | PaddleOCR | 2.8.0 |
| 说话人分离 | pyannote | speaker-diarization-3.1 |

### 调用链路

```
客户端 → reelmind-server  (FastAPI, 端口 2588)
         │
         ├── 非 AI 请求 → PostgreSQL / Redis / 文件系统
         │
         └── AI 请求 → HTTP → reelmind-ai (FastAPI, 内部 2589)
                              │
                              ├── /pipeline/start     — 启动管线任务
                              ├── /pipeline/status    — 查询任务状态
                              ├── /config             — 管线配置读写
                              ├── /health             — GPU + 模型健康状态
                              │
                              └── Redis pub-sub — 进度推送
                                   └── reelmind-server SSE — 客户端实时进度
```

AI 结果写入共享 SQLite 数据库（`reelmind_ai.db`），`reelmind-server` 直读 SQLite 返回给前端（subtitles/scenes/frames/speakers/tags 接口）。

### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose (reelmind)                │
│                                                             │
│  ┌──────────────┐   ┌──────────────────┐   ┌──────────────┐    │
│  │ reelmind-    │   │ reelmind-         │   │ reelmind-    │    │
│  │ server       │   │ orchestrator      │   │ ai (GPU)     │    │
│  │ (slim,noGPU) │   │ (CPU scheduler)   │   │ (CUDA 12.4)  │    │
│  └──────┬───────┘   └──────────────────┘   └──────┬───────┘    │
│         │                  │                  │             │
│         │    ┌─────────────▼──────────┐       │             │
│         │    │   reelmind-ai (GPU)     │       │             │
│         │    │  TransNetV2 → YOLO →   │       │             │
│         │    │  OCR → CLIP → Whisper  │       │             │
│         │    └─────────────┬──────────┘       │             │
│         │                  │                  │             │
│  ┌──────▼───────┐   ┌──────▼───────┐         │             │
│  │ reelmind-    │   │ reelmind-    │         │             │
│  │ postgres     │   │ redis        │         │             │
│  │ (pgvector)   │   │ (7-alpine)   │         │             │
│  └──────────────┘   └──────────────┘         │             │
└─────────────────────────────────────────────────────────────┘
```

### 环境变量

关键环境变量（通过 `.env` 配置）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_WHISPER` | `false` | 启用语音转文字 |
| `WHISPER_MODEL` | `tiny` | Whisper 模型规格（tiny/base/small/medium/large-v3） |
| `ENABLE_CLIP` | `false` | 启用 CLIP 语义搜索 |
| `HUGGINGFACE_TOKEN` | — | HuggingFace 令牌（pyannote 说话人分离需要） |
| `AI_SERVICE_URL` | `http://reelmind-ai:2589` | AI 容器地址（server 自动设定） |
| `AI_MEM_LIMIT` | `4g` | AI 容器内存上�