 # 批量 Pipeline 流程

 ## 触发入口

 | 方式 | 描述 |
 |------|------|
 | **手动批量处理** | 前端点击按钮 → `POST /api/ai/process-pending?limit={batchSize}` |
 | **自动运行 (Auto-Run)** | 后台线程每 `check_interval` 分钟检查条件，全部满足则触发 |

 ## Auto-Run 触发条件

 1. **有待处理视频** — DB 中存在 `status = 'pending'` 的视频
 2. **在时间窗口内** — 当前时间在 `auto_run_start_hour` ~ `auto_run_end_hour` 之间
 3. **GPU 空闲** — 通过 `nvidia-smi` 检测显存使用率低于阈值
 4. **无活跃任务** — 无正在运行的扫描/处理任务

 ## 完整处理流程

 触发入口 → 服务端预过滤 → AI 容器逐步骤执行

 **服务端 (reelmind-server):**
 1. 获取配置 `_get_pipeline_config()` — batch_size、max_file_size_mb 等
 2. 查询 DB 中待处理的视频（scene/yolo/ocr/clip/transcript_status = pending）
 3. 预过滤：文件不存在/不可读标记 error，Rendered 文件或过大跳过
 4. POST `/pipeline/start` 发送给 AI 容器
 5. 轮询 GET `/pipeline/status/{task_id}`（每 3s），通过 SSE 推送到前端

 **AI 容器 (reelmind-ai) — 每个视频依次执行:**
 - Step 1: Scene 检测 (TransNetV2) → 生成 scene 列表 + 缩略图
 - Step 2: 逐场景并行 → YOLO（对象检测）+ OCR（文字识别）+ CLIP（特征向量）
 - Step 3: 音频处理 → Whisper（语音转文字）+ Diarization（说话人分离）
 - 结果写入 DB，每个步骤有独立状态字段

 ## 配置来源

 所有配置从 AI 容器的 `/config` API 获取，通过 `_get_pipeline_config()` 读取:

 - `batch_size` — 每批处理的最大视频数（默认 10）
 - `max_file_size_mb` — 单文件大小上限，超过则跳过（默认 500）
 - `auto_run_enabled` — 是否启用自动运行
 - `auto_run_start_hour` / `auto_run_end_hour` — 自动运行时间窗口
 - `auto_run_gpu_threshold` — GPU 空闲阈值
 - `auto_run_check_interval` — 检查间隔（分钟）

 ## 状态字段

 每个 AI 步骤完成后，DB 中对应视频的状态字段更新到 `completed` 或 `error`:

 - `scene_status` — TransNetV2 场景检测
 - `yolo_status` — YOLO 对象检测
 - `ocr_status` — OCR 文字识别
 - `clip_status` — CLIP 特征向量
 - `transcript_status` — Whisper 转录 + Diarization

 ## 文件过滤规则

 在 `_process_pending_videos()` 中，每个待处理视频依次检查:

 1. `original_path` 是否存在 → 不存在标记 error 并跳过
 2. 文件名以 `Rendered - ` 开头且为 `.mov` → 跳过
 3. `ffprobe` 是否能读取 → 不能则标记 error
 4. OpenCV (cv2) 是否能读取 → 不能则尝试 ffmpeg，仍不能则标记 error
 5. `file_size > max_file_size_bytes` → 跳过

 标记为 error 的视频不会再次进入待处理队列（除非手动重置）。
 跳过的视频保留原 pending 状态，下次批处理仍会尝试。
