#!/usr/bin/env sh
set -e
mkdir -p /app/data
# Migrations are applied by the app on startup (see rentwise.main._auto_migrate).
# Set RENTWISE_AUTO_MIGRATE=false to disable.
exec uvicorn rentwise.main:app --host 0.0.0.0 --port 8000
