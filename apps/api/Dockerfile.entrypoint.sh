#!/usr/bin/env sh
set -e
mkdir -p /app/data
echo "Running alembic upgrade head..."
alembic upgrade head
exec uvicorn rentwise.main:app --host 0.0.0.0 --port 8000
