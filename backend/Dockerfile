# --- Base image ---
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps needed to build psycopg2 and friends, plus git for
# repository cloning (Milestone 3 onboarding).

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        git \
        util-linux \
    && rm -rf /var/lib/apt/lists/*
# Install Python dependencies first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Run as a non-root user. The workspace root (where repositories get cloned
# for onboarding/analysis) is created and owned by that user up front, since
# WORKSPACE_ROOT typically points outside /app (e.g. a mounted volume).
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /workspaces /milvus-data \
    && chown -R appuser:appuser /workspaces /milvus-data
USER root

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
