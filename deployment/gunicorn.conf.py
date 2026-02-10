"""
deployment/gunicorn.conf.py – Production-grade Gunicorn configuration
for Multi-Tenant JLPT (mikan.uz)

Key Design Decisions:
  - gthread worker class: Handles I/O-bound Django views efficiently
    (DB queries, S3 uploads) without the memory overhead of multiple processes.
  - workers = (2 * CPU) + 1: Standard Gunicorn formula for CPU utilization.
  - threads = 4: Each worker handles 4 concurrent requests via threading.
  - max_requests + jitter: Prevents memory leaks by recycling workers.
  - graceful_timeout = 120: Allows long exam submissions to complete.
  - preload_app: Shares application code memory across workers (CoW).

Usage:
  gunicorn config.wsgi:application --config deployment/gunicorn.conf.py
"""

import multiprocessing
import os

# =============================================================================
# SERVER SOCKET
# =============================================================================

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# =============================================================================
# WORKER PROCESSES
# =============================================================================

# Formula: (2 * CPU_COUNT) + 1
# - Provides good balance between throughput and resource usage
# - ENV override for containerized environments with CPU limits
workers = int(os.getenv("GUNICORN_WORKERS", (2 * multiprocessing.cpu_count()) + 1))

# gthread: Uses threads within each worker process
# - More memory efficient than 'sync' for I/O-bound apps (Django + DB)
# - Each worker spawns `threads` number of threads
# - Total concurrent requests = workers × threads
worker_class = "gthread"

# Threads per worker
# - 4 threads × N workers = 4N concurrent requests
# - Good for Django: most time is spent waiting on DB/Redis/S3
threads = int(os.getenv("GUNICORN_THREADS", 4))

# =============================================================================
# WORKER LIFECYCLE (Memory Leak Prevention)
# =============================================================================

# Recycle workers after N requests to prevent memory leaks
# - Django ORM query caches, file handles, etc. accumulate over time
# - 1000 requests is a safe threshold for long-running processes
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", 1000))

# Add random jitter to prevent all workers from restarting simultaneously
# - Workers restart between max_requests and max_requests + max_requests_jitter
# - Prevents "thundering herd" restart storms
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", 50))

# =============================================================================
# TIMEOUTS
# =============================================================================

# Worker timeout (seconds): Kill workers that are silent for this long
# - 120s accommodates:
#   - Large exam submissions (scoring + DB writes)
#   - Bulk material uploads (100MB files via S3)
#   - Complex analytics queries across tenant schemas
timeout = int(os.getenv("GUNICORN_TIMEOUT", 120))

# Graceful timeout: Time to finish current request after SIGTERM
# - Must be >= timeout to allow in-flight requests to complete
# - Critical for exam submissions: a student shouldn't lose answers
#   because a container is scaling down
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 120))

# Time to wait for requests on a Keep-Alive connection
# - 5s is sufficient; Nginx handles client-facing keep-alive
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 5))

# =============================================================================
# SECURITY
# =============================================================================

# Limit request line size (URL + headers) to prevent abuse
limit_request_line = 8190

# Limit number of headers
limit_request_fields = 100

# Limit header field size
limit_request_field_size = 8190

# =============================================================================
# PRELOADING
# =============================================================================

# Preload application code before forking workers
# Benefits:
#   - Shared memory via Copy-on-Write (saves ~30-50MB per worker)
#   - Faster worker startup (app already loaded)
# Caveat:
#   - DB connections established before fork are NOT shared;
#     Django creates new connections per-thread, so this is safe.
preload_app = True

# =============================================================================
# LOGGING
# =============================================================================

# Access log: stdout for Docker log aggregation (Loki/ELK/CloudWatch)
accesslog = "-"

# Error log: stdout for Docker log aggregation
errorlog = "-"

# Log level: info for production (captures startup, worker lifecycle)
# Use 'debug' only for troubleshooting; very verbose
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Access log format (JSON-compatible for structured logging)
# Fields: remote_addr, request_line, status, response_length, request_time, user_agent
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'
)

# =============================================================================
# PROCESS NAMING
# =============================================================================

# Set process title for `ps aux | grep gunicorn` visibility
proc_name = "jlpt_gunicorn"

# =============================================================================
# SERVER MECHANICS
# =============================================================================

# Forward X-Forwarded-* headers from Nginx
# Required for:
#   - SECURE_PROXY_SSL_HEADER to detect HTTPS
#   - REMOTE_ADDR resolution for rate limiting / django-axes
forwarded_allow_ips = os.getenv("GUNICORN_FORWARDED_ALLOW_IPS", "*")

# Reuse port (SO_REUSEPORT) – faster restarts, no "Address already in use"
reuse_port = True

# Temporary file directory for worker heartbeat files
# /dev/shm is a tmpfs (RAM-backed) – faster than disk for heartbeats
# Falls back to /tmp if /dev/shm is not available (non-Linux)
tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else "/tmp"

# =============================================================================
# SERVER HOOKS
# =============================================================================


def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info(
        "Gunicorn starting: workers=%s, threads=%s, worker_class=%s, timeout=%s",
        server.cfg.workers,
        server.cfg.threads,
        server.cfg.worker_class,
        server.cfg.timeout,
    )


def post_fork(server, worker):
    """Called just after a worker has been forked.

    Close any inherited DB connections so each worker gets its own.
    Django's connection handling will create new ones on demand.
    """
    from django.db import connections

    for conn in connections.all():
        conn.close()
    server.log.info("Worker spawned: pid=%s", worker.pid)


def worker_exit(server, worker):
    """Called when a worker exits (graceful or crash)."""
    server.log.info("Worker exiting: pid=%s", worker.pid)
