# Multi-stage Dockerfile for Multi-Tenant JLPT (mikan.uz)
# Stage 1: builder
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY deployment/requirements-deploy.txt ./
RUN pip install --user -r requirements.txt -r requirements-deploy.txt

# Stage 2: runtime
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system --gid 1000 app \
    && adduser --system --uid 1000 --gid 1000 --no-create-home app

COPY --from=builder /root/.local /home/app/.local
RUN chown -R app:app /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH

COPY --chown=app:app . .
RUN mkdir -p /app/staticfiles /app/media /app/logs && chown -R app:app /app/staticfiles /app/media /app/logs

USER app
EXPOSE 8000

# Default: Gunicorn (override in docker-compose for daphne/celery)
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
