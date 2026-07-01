#!/bin/bash
set -e

echo "==> ReelMind entrypoint: running Alembic migrations..."
alembic upgrade head

echo "==> Starting ReelMind server..."
if [ "${DEBUG}" = "true" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-2588} --reload --workers 1
else
    exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-2588} --workers 1
fi
