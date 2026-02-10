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
    
    # Extract password from REDIS_URL if present (redis://:password@host:port/db)
    local redis_password=""
    if echo "$REDIS_URL" | grep -q '://:.\+@'; then
        redis_password=$(echo "$REDIS_URL" | sed -n 's|.*://:\([^@]*\)@.*|\1|p')
    fi
    
    while [ $attempt -le $max_attempts ]; do
        local ping_ok=0
        if [ -n "$redis_password" ]; then
            # Authenticated Redis
            if timeout 2 redis-cli -u "$REDIS_URL" ping >/dev/null 2>&1; then
                ping_ok=1
            elif timeout 2 redis-cli -a "$redis_password" PING >/dev/null 2>&1; then
                ping_ok=1
            fi
        else
            # Unauthenticated Redis
            if timeout 2 redis-cli -u "$REDIS_URL" ping >/dev/null 2>&1 || \
               timeout 2 redis-cli PING >/dev/null 2>&1; then
                ping_ok=1
            fi
        fi
        
        if [ $ping_ok -eq 1 ]; then
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
# CRITICAL FIX: The advisory lock AND migrations MUST run inside the SAME
# database session (Python process). pg_try_advisory_lock is session-scoped:
# it releases automatically when the connection/session closes. If we
# acquired the lock in one `python manage.py shell` invocation and then
# ran `python manage.py migrate` in a separate process, the lock would
# already be released before migrations even start — defeating its purpose.
#
# Solution: A single Python script acquires the lock, runs both public and
# tenant migrations via Django's call_command(), and only releases the lock
# (by closing the session) AFTER all migrations complete.
#
# Lock ID: 0xDEADBEEF = 3735928559 (arbitrary but fixed)
# Reference: https://www.postgresql.org/docs/current/explicit-locking.html
##############################################################################
run_migrations_with_lock() {
    log_info "Attempting to acquire PostgreSQL advisory lock and run migrations..."

    python << 'MIGRATE_SCRIPT'
import sys
import time

# Bootstrap Django before any ORM usage
import django
django.setup()

from django.db import connection
from django.core.management import call_command

LOCK_ID = 3735928559  # 0xDEADBEEF
MAX_WAIT = 60         # seconds to wait for the lock
POLL_INTERVAL = 2     # seconds between retries

def run():
    """Acquire advisory lock, run migrations, then exit (releasing the lock)."""
    elapsed = 0

    # --- Acquire the advisory lock (non-blocking retry loop) ---
    while elapsed < MAX_WAIT:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_ID])
            acquired = cursor.fetchone()[0]

        if acquired:
            print(f"[OK] Advisory lock acquired (ID: {LOCK_ID})")
            break

        print(f"[WAIT] Lock held by another container, retrying in {POLL_INTERVAL}s... ({elapsed}/{MAX_WAIT}s)")
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    else:
        print(f"[ERROR] Could not acquire migration lock after {MAX_WAIT}s. Another migration is still running.")
        sys.exit(1)

    # --- Run migrations while we hold the lock (same session!) ---
    try:
        print("[MIGRATE] Step 1/2: Public schema migration (manage.py migrate --noinput)...")
        call_command("migrate", "--noinput")
        print("[OK] Public schema migrated successfully.")

        print("[MIGRATE] Step 2/2: Tenant schema migration (manage.py migrate_tenants --skip-public)...")
        try:
            call_command("migrate_tenants", "--skip-public")
            print("[OK] All tenant schemas migrated successfully.")
        except Exception as e:
            # migrate_tenants may not exist if not using django-tenants; treat as non-fatal warning
            if "Unknown command" in str(e):
                print(f"[WARN] migrate_tenants command not found, skipping tenant migrations: {e}")
            else:
                raise

        print("[OK] All migrations completed successfully.")
    except Exception as exc:
        print(f"[ERROR] Migration failed: {exc}")
        sys.exit(1)
    finally:
        # Explicitly release the advisory lock (good practice, though session
        # close would release it anyway).
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])
            print(f"[OK] Advisory lock released (ID: {LOCK_ID})")
        except Exception:
            pass  # Lock will be released when session closes regardless

run()
MIGRATE_SCRIPT

    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        log_error "Migration script exited with code $exit_code"
        return 1
    fi

    log_info "✓ Migrations completed successfully"
    return 0
}

##############################################################################
# 4) PGBOUNCER USERLIST PASSWORD INJECTION
#
# The template deployment/userlist.txt contains ${POSTGRES_PASSWORD}.
# At runtime, envsubst replaces it with the actual password from the
# environment. This avoids baking secrets into the Docker image.
#
# Only the 'web' service runs this (it's the migration leader), but
# we provide it for any service that mounts the PgBouncer volume.
##############################################################################
inject_pgbouncer_password() {
    local template="/app/deployment/userlist.txt"
    local target="/etc/pgbouncer/userlist.txt"

    # Only run if the template exists AND we have write access to the target dir
    if [ -f "$template" ] && [ -d "$(dirname "$target")" ]; then
        if command -v envsubst >/dev/null 2>&1; then
            log_info "Injecting POSTGRES_PASSWORD into PgBouncer userlist.txt..."
            envsubst < "$template" > "$target"
            chmod 600 "$target" 2>/dev/null || true
            log_info "✓ PgBouncer userlist.txt updated"
        else
            log_warn "envsubst not found, using sed fallback for PgBouncer userlist.txt"
            sed "s/\${POSTGRES_PASSWORD}/${POSTGRES_PASSWORD}/g" "$template" > "$target" 2>/dev/null || true
        fi
    fi
}

##############################################################################
# 5) COLLECT STATIC FILES (only if not already collected)
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
# 6) MAIN DISPATCHER – Route to appropriate service
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
    
    # Step 2: Inject PgBouncer password (if template exists)
    inject_pgbouncer_password
    
    # Step 3: Run migrations (only for 'web' service; others skip)
    if [ "$service" = "web" ]; then
        log_info "=== MIGRATION PHASE ==="
        if ! run_migrations_with_lock; then
            log_error "Migration phase failed. Aborting startup."
            exit 1
        fi
        
        # Step 4: Collect static files
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
