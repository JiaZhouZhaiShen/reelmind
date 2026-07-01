# syntax=docker/dockerfile:1
# ReelMind Orchestrator — lightweight job scheduler (CPU-only, no volumes)
FROM python:3.12-slim

WORKDIR /app

COPY server/orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/orchestrator/main.py .
COPY server/orchestrator/log_setup.py .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["python3", "main.py"]
