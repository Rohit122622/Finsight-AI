# ──────────────────────────────────────────────────────────────
# FinSentry AI — Backend Dockerfile (multi-stage)
# ──────────────────────────────────────────────────────────────
# Stage 1: Builder — installs dependencies and compiles wheels
# Stage 2: Production — lean runtime image
# ──────────────────────────────────────────────────────────────

# ── Stage 1: Builder ─────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# Install build-time system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Production Runtime ──────────────────────────────
FROM python:3.13-slim AS production

# Labels
LABEL maintainer="FinSentry AI Team"
LABEL description="FinSentry AI Backend API"
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

# Runtime environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

# Switch to non-root user
USER finsentry

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--loop", "uvloop", "--http", "httptools"]