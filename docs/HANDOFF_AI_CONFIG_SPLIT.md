# ReelMind AI 容器配置拆分 — 交接文档

## 整体完成度 — 85%

| 阶段 | 完成 | 说明 |
|------|------|------|
| 配置拆分 | 100% | 6 个模块 + pipeline 各独立文件，JSON 持久化 |
| API 端点 | 100% | 新增 /config/{module} GET/POST，旧 API 兼容保留 |
| Pipeline 对接 | 100% | pipeline.py 已从 configs 包读取配置 |
| 容器部署 | 100% | volume mount + --reload，改代码无需 rebuild |
| Server 同步 | 0% | server/app/api/ai.py 的 _pipeline_steps 未同步 |
| 环境变量治理 | 50% | pipeline.py 仍依赖 ENABLE_WHISPER/ENABLE_CLIP |

## 当前进度（本轮完成）

**核心交付：**
- 9 个新增文件 -> server/ai_service/configs/ 全套配置包
- 3 个修改文件 -> main.py（新端点）、pipeline.py（对接 configs）、docker-compose.yml（开发体验）
- 1 个删除文件 -> AI_ENGINE_PROGRESS.md

**验证结果（全部通过）：**
- GET /config/yolo / whisper / ocr / scene / clip / diarization / pipeline -> 正常返回
- POST /config/yolo {"config":{"enabled":false}} -> 保存成功，持久化确认
- GET /config/unknown -> 404
- /health -> GPU 8GB, 5 个模型在线

## 后续任务

### P0 — Server 端状态同步
server/app/api/ai.py 有独立的 _pipeline_steps 字典，与 AI 容器配置系统未同步。Web UI 改配置后，server 需转发到 AI 容器的 /config/{module} 接口。

### P1 — 环境变量治理
pipeline.py 仍有 os.environ.get('ENABLE_WHISPER') 和 ENABLE_CLIP 检查，建议统一走模块配置的 enabled 字段。

### P2 — 模型延迟加载
配置层已支持，后续按需加载模型只需在模块层面加 lazy_load 标志。

## 变更清单

### 新增 — 9 个文件
- configs/__init__.py — 入口：单例加载 + to_dict_all() + update_from_dict()
- configs/base.py — ModuleConfig 基类
- configs/scene_config.py — TransNetV2
- configs/yolo_config.py — YOLOv8n
- configs/ocr_config.py — PaddleOCR
- configs/clip_config.py — open-clip
- configs/whisper_config.py — faster-whisper
- configs/diarization_config.py — pyannote
- configs/pipeline_config.py — 管线调度

### 修改 — 3 个文件
- main.py — 添加 ModuleConfigRequest + /config/{module} 端点
- pipeline.py — import 改为 from configs import ...
- docker-compose.yml — volume mount + --reload

### 删除 — 1 个文件
- AI_ENGINE_PROGRESS.md

## 架构

### 配置生命周期
configs/__init__.py -> 内存单例 -> GET/POST /config/{module} -> JSON 持久化

### 持久化路径
{DATA_ROOT}/configs/{module}.json（默认 /data/reelmind/data/configs/）

### API 端点
- GET /config — 全部配置
- POST /config — 批量更新
- GET /config/{module} — 单个配置
- POST /config/{module} — 更新单个
- GET /health — 健康检查
- POST /pipeline/start — 启动管线
- GET /pipeline/status/{task_id} — 任务状态
- POST /pipeline/cancel/{task_id} — 取消任务

## 开发指引
- 改代码无需 rebuild: volume mount + --reload 自动生效
- 添加新模块: configs/{name}_config.py + __init__.py 注册, main.py 不用改
- 启动: docker compose up -d reelmind-ai

## 当前运行状态
- AI 容器运行中, GPU 8GB
- 5 个模型在线 (transnet, yolo, ocr, whisper, clip)
- 7 个配置端点可读写
- 健康检查通过
