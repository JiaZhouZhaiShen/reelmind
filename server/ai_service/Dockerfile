# syntax=docker/dockerfile:1
# ReelMind AI Service — GPU + AI dependencies only
FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common gpg-agent \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv \
    ffmpeg curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && python3.12 -m ensurepip --upgrade \
    && python3.12 -m pip install --upgrade pip setuptools wheel \
    && ln -sf /usr/local/bin/pip3.12 /usr/bin/pip3 \
    && ln -sf /usr/local/bin/pip3.12 /usr/bin/pip

WORKDIR /app

# PyTorch (CUDA 12.4)
COPY server/ai_service/requirements.txt .
RUN pip install --no-cache-dir \
    torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
    --index-url https://download.pytorch.org/whl/cu124

# Other AI dependencies
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    -r requirements.txt

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_ENDPOINT=https://hf-mirror.com \
    PIP_DEFAULT_TIMEOUT=120

COPY server/ai_service/ .
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 2589

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "2589", "--workers", "1"]
