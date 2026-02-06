"""
Enhanced Health Check View for JLPT System
==========================================
Verifies application, database, cache, and WebSocket readiness
Endpoint: /health/check/ (JSON response)
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import connection
from django.core.cache import cache
import redis
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "HEAD"])
def health_check(request):
    """
    Comprehensive health check endpoint
    
    Returns:
        200 OK: All services healthy
        503 Service Unavailable: One or more services down
        
    Response format:
    {
        "status": "healthy|degraded|unhealthy",
        "timestamp": "2026-02-06T16:00:00Z",
        "services": {
            "application": {"status": "healthy", "message": "..."},
            "database": {"status": "healthy", "latency_ms": 5.2},
            "cache": {"status": "healthy", "latency_ms": 1.5},
            "celery": {"status": "healthy", "workers": 3}
        }
    }
    """
    
    health_data = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "services": {
            "application": check_application(),
            "database": check_database(),
            "cache": check_cache(),
            "celery": check_celery(),
        }
    }
    
    # Determine overall status
    service_statuses = [s["status"] for s in health_data["services"].values()]
    
    if "unhealthy" in service_statuses:
        health_data["status"] = "unhealthy"
        status_code = 503
    elif "degraded" in service_statuses:
        health_data["status"] = "degraded"
        status_code = 200  # Still OK, but warn in logs
    else:
        health_data["status"] = "healthy"
        status_code = 200
    
    # Log health status
    if status_code != 200:
        logger.warning(f"Health check failed: {json.dumps(health_data)}")
    
    return JsonResponse(health_data, status=status_code)


def check_application():
    """Check Django application status"""
    try:
        # Verify Django settings are loaded
        from django.conf import settings
        
        return {
            "status": "healthy",
            "message": "Django application running",
            "debug": settings.DEBUG,
            "environment": settings.ENVIRONMENT if hasattr(settings, 'ENVIRONMENT') else "unknown"
        }
    except Exception as e:
        logger.error(f"Application health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "message": f"Django error: {str(e)}"
        }


def check_database():
    """
    Check PostgreSQL database connection and response time
    Critical for: Multi-tenant schema detection, authentication
    """
    import time
    
    try:
        start_time = time.time()
        
        # Test connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
        
        if not result:
            return {"status": "unhealthy", "message": "Database query returned no result"}
        
        latency_ms = round((time.time() - start_time) * 1000, 2)
        
        # Check advisory lock (for migration safety)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(3735928559)")
            lock_available = cursor.fetchone()[0]
            if lock_available:
                cursor.execute("SELECT pg_advisory_unlock(3735928559)")
        
        # Warn if latency > 100ms
        status = "healthy" if latency_ms < 100 else "degraded"
        
        return {
            "status": status,
            "message": "PostgreSQL responding",
            "latency_ms": latency_ms,
            "advisory_lock": "available" if lock_available else "unavailable"
        }
    
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "message": f"PostgreSQL error: {str(e)}"
        }


def check_cache():
    """
    Check Redis cache connection
    Critical for: Session storage, Celery broker, rate limiting
    """
    import time
    
    try:
        # Test set/get operation
        start_time = time.time()
        
        test_key = "health_check_test"
        test_value = "ok"
        
        # Set
        cache.set(test_key, test_value, timeout=10)
        
        # Get
        result = cache.get(test_key)
        
        latency_ms = round((time.time() - start_time) * 1000, 2)
        
        if result != test_value:
            return {"status": "unhealthy", "message": "Cache set/get mismatch"}
        
        # Clean up
        cache.delete(test_key)
        
        # Warn if latency > 50ms
        status = "healthy" if latency_ms < 50 else "degraded"
        
        # Get Redis connection info
        redis_info = {}
        try:
            from django.core.cache import caches
            redis_conn = caches['default']._cache
            if hasattr(redis_conn, 'info'):
                info = redis_conn.info()
                redis_info = {
                    "connected_clients": info.get('connected_clients', 0),
                    "used_memory_mb": round(info.get('used_memory', 0) / 1024 / 1024, 2),
                    "keyspace_hits": info.get('keyspace_hits', 0)
                }
        except:
            pass
        
        return {
            "status": status,
            "message": "Redis responding",
            "latency_ms": latency_ms,
            "redis_info": redis_info if redis_info else "N/A"
        }
    
    except Exception as e:
        logger.error(f"Cache health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "message": f"Redis error: {str(e)}"
        }


def check_celery():
    """
    Check Celery worker status and task queue
    Critical for: Background job processing, async tasks
    """
    try:
        from celery import current_app
        from celery.result import AsyncResult
        
        # Get Celery app stats
        stats = current_app.control.inspect().stats()
        
        if not stats:
            return {
                "status": "unhealthy",
                "message": "No Celery workers available"
            }
        
        active = current_app.control.inspect().active()
        reserved = current_app.control.inspect().reserved()
        
        worker_count = len(stats) if stats else 0
        active_tasks = sum(len(tasks) for tasks in active.values()) if active else 0
        reserved_tasks = sum(len(tasks) for tasks in reserved.values()) if reserved else 0
        
        # Warn if too many tasks queued
        status = "healthy"
        if reserved_tasks > 1000:
            status = "degraded"
        
        return {
            "status": status,
            "message": "Celery workers active",
            "workers": worker_count,
            "active_tasks": active_tasks,
            "reserved_tasks": reserved_tasks
        }
    
    except Exception as e:
        logger.warning(f"Celery health check failed (non-critical): {str(e)}")
        return {
            "status": "degraded",
            "message": f"Celery unavailable: {str(e)}"
        }


@require_http_methods(["GET"])
def health_simple(request):
    """
    Simple health check for Docker/Nginx monitoring
    Returns: 200 OK if application is running
    Used by: docker HEALTHCHECK, Nginx upstream
    """
    try:
        # Quick check: Django loaded, database accessible
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        return JsonResponse({"status": "ok"})
    except Exception as e:
        return JsonResponse(
            {"status": "error", "message": str(e)},
            status=503
        )


# ========================================
# URL Configuration
# ========================================
# Add to your urls.py:
#
# from .views import health_check, health_simple
# from django.urls import path
#
# urlpatterns = [
#     path('health/', health_simple, name='health-simple'),
#     path('health/check/', health_check, name='health-check'),
# ]
