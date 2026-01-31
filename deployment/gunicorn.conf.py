"""
Gunicorn configuration for Multi-Tenant JLPT (mikan.uz).
For systemd: use bind 127.0.0.1:8000 (behind Nginx).
For Docker: override with GUNICORN_BIND=0.0.0.0:8000.
"""

import multiprocessing
import os

# Server socket
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8000")
backlog = 2048

# Worker processes
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 300
keepalive = 5

# Logging (use files for systemd deploy, or "-" for Docker/journal)
_log_dir = os.getenv("GUNICORN_LOG_DIR", "")
if _log_dir:
    accesslog = os.path.join(_log_dir, "gunicorn_access.log")
    errorlog = os.path.join(_log_dir, "gunicorn_error.log")
else:
    accesslog = "-"
    errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "jlpt_gunicorn"

# Server mechanics
daemon = False
pidfile = os.getenv("GUNICORN_PIDFILE", None)
user = None
group = None
tmp_upload_dir = None

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Preload (faster worker startup; disable if CONN_MAX_AGE / DB issues)
preload_app = os.getenv("GUNICORN_PRELOAD", "false").lower() == "true"

# Environment
raw_env = [
    "DJANGO_SETTINGS_MODULE=config.settings.production",
]

# Hooks
def post_fork(server, worker):
    """Reset DB connections after fork so each worker gets its own."""
    from django.db import connection
    connection.close()

def when_ready(server):
    server.log.info("Gunicorn ready. Spawning workers...")

def worker_int(worker):
    worker.log.info("Worker received INT/QUIT (pid: %s)", worker.pid)
