# Multi-stage Dockerfile for Multi-Tenant JLPT (mikan.uz)
# ============================================================================
# Stage 1: builder – Compile Python packages
# ============================================================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300

WORKDIR /app

# Install build dependencies (gcc, libpq-dev) – will be discarded in runtime stage
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and build wheels
COPY requirements.txt deployment/requirements-deploy.txt ./
RUN pip install --user --no-warn-script-location \
    -r requirements.txt \
    -r requirements-deploy.txt

# ============================================================================
# Stage 2: runtime – Minimal production image
# ============================================================================
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/app/.local/bin:$PATH

WORKDIR /app

# Install only runtime dependencies:
#   - libpq5: PostgreSQL client library (required by psycopg2)
#   - postgresql-client: provides pg_isready (used by wait_for_postgres)
#   - redis-tools: provides redis-cli (used by wait_for_redis)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (UID 1000 for consistency with volumes)
RUN addgroup --system --gid 1000 app && \
    adduser --system --uid 1000 --gid 1000 --no-create-home app

# Copy pre-built Python packages from builder stage
COPY --from=builder --chown=app:app /root/.local /home/app/.local

# Copy application code and set permissions
COPY --chown=app:app . .

# Create required directories for staticfiles, media, logs
RUN mkdir -p /app/staticfiles /app/media /app/logs && \
    chown -R app:app /app/staticfiles /app/media /app/logs

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Switch to non-root user
USER app

# Expose standard ports (actual port depends on service)
EXPOSE 8000 8001

# NOTE: No Dockerfile-level HEALTHCHECK. Each service (web, daphne, celery,
# beat) listens on different ports or no port at all. Per-service healthchecks
# are defined in docker-compose.yml and docker-compose.prod.yml instead.

# Entrypoint: robust startup script that handles all services
# Usage:
#   docker run ... entrypoint.sh web        # Gunicorn (HTTP)
#   docker run ... entrypoint.sh daphne     # Daphne (WebSocket)
#   docker run ... entrypoint.sh celery     # Celery worker
#   docker run ... entrypoint.sh beat       # Celery beat (scheduler)
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
