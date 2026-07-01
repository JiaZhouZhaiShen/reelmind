flowchart TD
    %% ── Style Definitions ──
    classDef frontend fill:#1e293b,stroke:#6366f1,color:#e2e8f0
    classDef server fill:#1e3a5f,stroke:#3b82f6,color:#e2e8f0
    classDef ai fill:#3b1f3b,stroke:#a855f7,color:#e2e8f0
    classDef db fill:#1a3a2a,stroke:#22c55e,color:#e2e8f0
    classDef flow fill:transparent,stroke:#f59e0b,stroke-dasharray:5 5,color:#f59e0b

    subgraph front ["🧩 前端 React (AIEnginePage + PipelineConfigPanel)"]
        direction TB
        F0["Ai数据总览 (轮询 3s)"] --> F1["选择处理模式: 手动批量 / 自动批量 / 单视频"]
        F1 --> F2["选择 AI 引擎: 场景/YOLO/OCR/CLIP/转录/说话人分离"]
        F2 --> F3["配置参数: 每批数量 / 超时 / 文件过滤"]
        F3 --> F4["保存配置 (POST /pipeline/manual/config)"]
        F3 --> F5["立即开始 (POST /pipeline/manual/start)"]
        F5 --> F6{"检查锁定: 取消已有 running 批"}
        F6 --> F7["显示实时进度: BatchProgressSection"]
        F7 --> F8["轮询: listBatchCheckpoints(5s) + getBatchEngineProgress(3s)"]
        F8 --> F9["渲染: 分引擎进度条 (BlockBar) + 总体进度条"]
    end

    subgraph svr ["⚙️ 后端 Server (FastAPI /ai 路由)"]
        direction TB
        S1["POST pipeline/manual/start"]
        S1 --> S2["重置 ai_engine_jobs 到 pending (rerun 模式)"]
        S2 --> S3["创建 BatchCheckpoint (status=running)"]
        S3 --> S4["生成后台线程 _orchestrate_batch()"]
        S4 --> S5["查询待处理 media_ids (pending videos)"]
        S5 --> S6["应用文件过滤: 大小/时长/跳过渲染文件"]
        S6 --> S7["分批处理 (chunk, 每批 batch_size 个视频)"]
        S7 --> S8["更新 current_chunk_ids"]
        S8 --> S9["&nbsp;HTTP POST → AI 容器 /pipeline/start"]
        S9 --> S10["轮询 wait_for_completion (2s)"]
        S10 --> S11{"AI 容器返回完成?"}
        S11 -- "是" --> S12["更新 BatchCheckpoint.processed"]
        S12 --> S13["查询 ai_engine_jobs 分引擎进度"]
        S13 --> S14["更新 checkpoint.engine_progress (JSONB)"]
        S14 --> S15{"还有未处理 chunk?"}
        S15 -- "是" --> S7
        S15 -- "否" --> S16["标记 checkpoint status=completed"]
        S11 -- "超时/错误" --> S17["记录错误日志, 继续下一批"]
        S17 --> S12
    end

    subgraph ai_cont ["🤖 AI 容器 (Python)"]
        direction TB
        A1["接收 POST /pipeline/start"]
        A1 --> A2["process_batch() 主循环"]
        A2 --> A3["STEP 1: TransNetV2 场景检测"]
        A3 --> A4["提取场景缩略图, 写入 SQLite"]
        A4 --> A5["更新 ai_engine_jobs (scene=completed)"]
        A5 --> A6["STEP 2: YOLO 物体检测 (逐场景)"]
        A6 --> A7["写入 SQLite SceneTag 表"]
        A7 --> A8["更新 ai_engine_jobs (yolo=completed)"]
        A8 --> A9["STEP 3: PaddleOCR 文字识别 (逐场景)"]
        A9 --> A10["写入 SQLite SceneOCR 表"]
        A10 --> A11["更新 ai_engine_jobs (ocr=completed)"]
        A11 --> A12["STEP 4: OpenCLIP 语义编码 (逐场景)"]
        A12 --> A13["写入 SQLite Frame (embedding) 表"]
        A13 --> A14["更新 ai_engine_jobs (clip=completed)"]
        A14 --> A15["STEP 5: faster-whisper 语音转录"]
        A15 --> A16["写入 SQLite Subtitle 表"]
        A16 --> A17["更新 ai_engine_jobs (transcript=completed)"]
        A17 --> A18["（可选）pyannote 说话人分离"]
        A18 --> A19["更新 Subtitle.speaker 字段"]
        A19 --> A20["更新 ai_engine_jobs (diarization=completed)"]
        A20 --> A21["生成 WebVTT 字幕文件"]
        A21 --> A22["返回 status=completed"]
    end

    subgraph pg ["💾 PostgreSQL"]
        direction TB
        P1["batch_checkpoints<br/>表: 批次跟踪"]
        P2["ai_engine_jobs<br/>表: 每视频每引擎状态"]
        P3["assets 表<br/>媒体元数据"]
    end

    subgraph sqlite ["💿 SQLite (AI 容器内)"]
        direction TB
        Q1["Video / Scene / Frame<br/>Subtitle / SceneTag / SceneOCR"]
    end

    %% ── Cross-subgraph flows ──
    F5 -.->|REST API| S1
    F8 -.->|轮询 GET| S1
    S9 -.->|HTTP POST| A1
    A11 -.->|直接 PG 写入| P2
    S12 -.-> P1
    S13 -.-> P2
    S3 -.-> P1
    A4 -.-> Q1
    A7 -.-> Q1
    A10 -.-> Q1
    A13 -.-> Q1
    A16 -.-> Q1
    A19 -.-> Q1

    %% ── Data flow legend ──
    L1["--- 图例 ---"]:::flow
    L2["🧩 前端层"]:::frontend
    L3["⚙️ 后端 Server 层"]:::server
    L4["🤖 AI 容器层"]:::ai
    L5["💾 PostgreSQL 持久化"]:::db
    L6["💿 SQLite(AI 容器)"]:::db
    L7["-.- HTTP/REST API 调用"]:::flow
