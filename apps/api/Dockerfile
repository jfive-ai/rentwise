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

EXPOSE 8000

# Use --reload in dev (overridden in docker-compose.yml for prod)
CMD ["uvicorn", "rentwise.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
