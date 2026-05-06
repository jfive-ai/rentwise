FROM python:3.12-slim

WORKDIR /app

# System deps for Playwright (needed even though Phase 0 doesn't use it; saves a rebuild later)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# App code
COPY rentwise/ ./rentwise/
COPY tests/ ./tests/
COPY alembic.ini .
COPY alembic/ ./alembic/

EXPOSE 8000

COPY Dockerfile.entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]
