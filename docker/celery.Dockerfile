# ──────────────────────────────────────────────────────────────
# FinSentry AI — Celery Worker Dockerfile (multi-stage)
# ──────────────────────────────────────────────────────────────
# Shares the same base build as backend but runs the Celery worker
# ──────────────────────────────────────────────────────────────

# ── Stage 1: Builder ─────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Production Runtime ──────────────────────────────
FROM python:3.13-slim AS production

LABEL maintainer="FinSentry AI Team"
LABEL description="FinSentry AI Celery Worker"
LABEL version="1.0.0"

# Create non-root user
RUN groupadd -r finsentry && useradd -r -g finsentry -d /app -s /sbin/nologin finsentry

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY backend/ .

# Create uploads directory with correct permissions
RUN mkdir -p /app/uploads && chown -R finsentry:finsentry /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Switch to non-root user
USER finsentry

# Health check: verify worker can inspect itself
HEALTHCHECK --interval=60s --timeout=15s --start-period=30s --retries=3 \
    CMD celery -A workers.celery_app inspect ping --timeout 10 || exit 1

CMD ["celery", "-A", "workers.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
