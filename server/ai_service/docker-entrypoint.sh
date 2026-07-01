#!/bin/bash
export CUBLAS_WORKSPACE_CONFIG=:4096:8
set -e

echo "==> ReelMind AI entrypoint: starting Uvicorn (foreground)"

export PYTHONPATH=/server:$PYTHONPATH

# 前台起 uvicorn（AI 管线 API）
 exec uvicorn main:app --host 0.0.0.0 --port 2589 --workers 1
