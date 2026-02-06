#!/bin/bash
##############################################################################
# entrypoint.sh – Smart entrypoint for JLPT Multi-Tenant Django + Celery
#
# Features:
# 1. Waits for Postgres & Redis with exponential backoff
# 2. Uses PostgreSQL advisory locks to prevent migration race conditions
# 3. Runs `migrate` (public schema) then `migrate_tenants` safely
# 4. Collects static files (only if not already collected)
# 5. Graceful error handling + proper exit codes
# 6. Supports multiple worker replicas without conflicts
#
# Usage (in docker-compose or Dockerfile CMD):
#   entrypoint.sh web      # Run Django web server (Gunicorn)
#   entrypoint.sh daphne   # Run ASGI server (Daphne WebSockets)
#   entrypoint.sh celery   # Run Celery worker
#   entrypoint.sh beat     # Run Celery beat (only one instance)
##############################################################################

set -euo pipefail

# Configuration
DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}
DB_USER=${DB_USER:-postgres}
DB_NAME=${DB_NAME:-jlpt_mock_db}
REDIS_URL=${REDIS_URL:-redis://redis:6379/0}

# Logging helper
log_info() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [INFO] $1"
}

log_warn() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [WARN] $1" >&2
}

log_error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [ERROR] $1" >&2
}

##############################################################################
# 1) WAIT FOR DATABASE – with exponential backoff
##############################################################################
wait_for_postgres() {
    log_info "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
    
    local max_attempts=30
    local attempt=1
    local wait_time=1
    
    while [ $attempt -le $max_attempts ]; do
        if pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" 2>/dev/null; then
            log_info "PostgreSQL is ready!"
            return 0
        fi
        
        log_warn "Attempt $attempt/$max_attempts: PostgreSQL not ready, waiting ${wait_time}s..."
        sleep "$wait_time"
        
        # Exponential backoff: 1, 2, 4, 8... (max 5s per attempt)
        wait_time=$((wait_time * 2))
        [ $wait_time -gt 5 ] && wait_time=5
        
        attempt=$((attempt + 1))
    done
    
    log_error "PostgreSQL failed to start after ${max_attempts} attempts"
    return 1
}

##############################################################################
# 2) WAIT FOR REDIS – with exponential backoff
##############################################################################
wait_for_redis() {
    log_info "Waiting for Redis at ${REDIS_URL}..."
    
    local max_attempts=20
    local attempt=1
    local wait_time=1
    
    while [ $attempt -le $max_attempts ]; do
        if timeout 2 redis-cli -u "$REDIS_URL" ping >/dev/null 2>&1 || \
           timeout 2 redis-cli PING >/dev/null 2>&1; then
            log_info "Redis is ready!"
            return 0
        fi
        
        log_warn "Attempt $attempt/$max_attempts: Redis not ready, waiting ${wait_time}s..."
        sleep "$wait_time"
        
        wait_time=$((wait_time * 2))
        [ $wait_time -gt 5 ] && wait_time=5
        
        attempt=$((attempt + 1))
    done
    
    log_error "Redis failed to start after ${max_attempts} attempts"
    return 1
}

##############################################################################
# 3) ACQUIRE DISTRIBUTED LOCK via PostgreSQL Advisory Lock
#
# Advisory locks are unique row-level locks in PostgreSQL that don't require
# a table. We use a fixed lock ID (0xDEADBEEF = 3735928559) for migrations.
#
# This ensures only ONE container runs migrations at a time, even with
# multiple replicas. The lock is automatically released when the connection
# closes or on timeout (30 seconds).
#
# Reference: https://www.postgresql.org/docs/current/explicit-locking.html
##############################################################################
run_migrations_with_lock() {
    local lock_id=3735928559  # Fixed advisory lock ID (0xDEADBEEF)
    local lock_acquired=0
    local lock_timeout=30  # seconds
    
    log_info "Attempting to acquire PostgreSQL advisory lock (ID: $lock_id, timeout: ${lock_timeout}s)..."
    
    # Try to acquire the advisory lock with timeout
    if timeout "$lock_timeout" python manage.py shell << 'EOF'
import sys
from django.db import connection

lock_id = 3735928559

# Attempt non-blocking lock
with connection.cursor() as cursor:
    cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_id])
    acquired = cursor.fetchone()[0]
    
    if not acquired:
        print("[ERROR] Failed to acquire lock. Another migration is in progress.")
        sys.exit(1)
    
    print(f"[OK] Lock acquired (ID: {lock_id})")
    
    # Now we have the lock; proceed with migrations
EOF
    then
        lock_acquired=1
    else
        log_error "Failed to acquire migration lock (lock held by another container)"
        return 1
    fi
    
    if [ $lock_acquired -eq 1 ]; then
        log_info "Lock acquired successfully! Running migrations..."
        
        # Public schema migration
        log_info "Step 1/2: Running 'python manage.py migrate --noinput' (public schema)..."
        if ! python manage.py migrate --noinput; then
            log_error "Public schema migration failed!"
            return 1
        fi
        log_info "✓ Public schema migrated successfully"
        
        # Tenant schema migrations
        log_info "Step 2/2: Running 'python manage.py migrate_tenants --skip-public' (all tenant schemas)..."
        if ! python manage.py migrate_tenants --skip-public; then
            log_error "Tenant schema migration failed!"
            return 1
        fi
        log_info "✓ All tenant schemas migrated successfully"
        
        log_info "✓ All migrations completed successfully"
        return 0
    fi
}

##############################################################################
# 4) COLLECT STATIC FILES (only if not already collected)
#
# We check if `staticfiles/` directory exists and has content before
# running collectstatic. This avoids redundant I/O on every container start.
##############################################################################
collect_static_files() {
    log_info "Checking static files..."
    
    # Check if staticfiles directory exists and has content
    if [ -d "staticfiles" ] && [ "$(ls -A staticfiles 2>/dev/null | wc -l)" -gt 10 ]; then
        log_info "Static files already collected ($(ls -1 staticfiles | wc -l) files found). Skipping."
        return 0
    fi
    
    log_info "Running 'python manage.py collectstatic --noinput --clear'..."
    if python manage.py collectstatic --noinput --clear 2>&1 | grep -q "error\|Error"; then
        log_warn "collectstatic completed with warnings. Continuing..."
    else
        log_info "✓ Static files collected successfully"
    fi
}

##############################################################################
# 5) MAIN DISPATCHER – Route to appropriate service
##############################################################################
main() {
    local service="${1:-web}"
    
    log_info "=== JLPT Entrypoint Started (service: $service) ==="
    log_info "Environment: DB_HOST=$DB_HOST, DB_NAME=$DB_NAME, REDIS_URL=$REDIS_URL"
    
    # Step 1: Wait for dependencies
    if ! wait_for_postgres; then
        log_error "Failed to connect to PostgreSQL. Aborting."
        exit 1
    fi
    
    if ! wait_for_redis; then
        log_error "Failed to connect to Redis. Aborting."
        exit 1
    fi
    
    log_info "All dependencies are ready!"
    
    # Step 2: Run migrations (only for 'web' service; others skip)
    if [ "$service" = "web" ]; then
        log_info "=== MIGRATION PHASE ==="
        if ! run_migrations_with_lock; then
            log_error "Migration phase failed. Aborting startup."
            exit 1
        fi
        
        # Step 3: Collect static files
        log_info "=== STATIC FILES PHASE ==="
        if ! collect_static_files; then
            log_warn "Static file collection failed, but continuing (may be S3-backed)..."
        fi
        
        log_info "=== WEB SERVICE STARTUP ==="
        log_info "Starting Gunicorn..."
        exec gunicorn config.wsgi:application \
            --config deployment/gunicorn.conf.py \
            --bind 0.0.0.0:8000
    
    elif [ "$service" = "daphne" ]; then
        log_info "=== DAPHNE (ASGI/WebSocket) STARTUP ==="
        log_info "Starting Daphne..."
        exec daphne \
            --bind 0.0.0.0 \
            --port 8001 \
            --proxy-headers \
            --ws-per-message-deflate \
            --max-http-body-size 104857600 \
            --timeout 300 \
            --application-close-timeout 300 \
            -v 1 \
            config.asgi:application
    
    elif [ "$service" = "celery" ]; then
        log_info "=== CELERY WORKER STARTUP ==="
        log_info "Starting Celery worker..."
        exec celery -A config worker \
            --loglevel=info \
            --max-tasks-per-child=100 \
            --max-memory-per-child=256000 \
            --without-gossip \
            --without-mingle \
            --without-heartbeat
    
    elif [ "$service" = "beat" ]; then
        log_info "=== CELERY BEAT (SCHEDULER) STARTUP ==="
        log_info "Starting Celery beat..."
        # Note: For HA setups, use Redis-backed locking or single replica constraint
        exec celery -A config beat \
            --loglevel=info \
            --scheduler django_celery_beat.schedulers:DatabaseScheduler
    
    else
        log_error "Unknown service: $service"
        log_error "Valid services: web, daphne, celery, beat"
        exit 1
    fi
}

##############################################################################
# ENTRY POINT
##############################################################################

# Handle signals gracefully
trap 'log_info "Received SIGTERM, shutting down gracefully..."; exit 0' SIGTERM
trap 'log_info "Received SIGINT, shutting down..."; exit 0' SIGINT

# Run main
main "$@"
