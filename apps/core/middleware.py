# apps/core/middleware.py
"""
Multi-tenant schema isolation middleware.

CRITICAL: Always reset to public schema at request start (connection may come from
pool with a tenant search_path) and at request end so connections returned to the
pool are safe for the next request.
"""
import logging
import threading
import uuid

from django.utils.deprecation import MiddlewareMixin

from apps.core.tenant_utils import set_public_schema, get_current_schema

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        """
        Reset to public schema at the start of every request to prevent schema
        pollution from connection pooling (CONN_MAX_AGE > 0). The connection
        may have been used by a previous tenant request.
        """
        try:
            set_public_schema()
            logger.debug(
                "TenantMiddleware.process_request: reset to public, path=%s",
                request.path,
            )
        except Exception as e:
            logger.exception("Failed to set public schema at request start: %s", e)
        return None

    def process_response(self, request, response):
        """
        CRITICAL: Always reset to public schema after request so the connection
        returned to the pool is safe for the next request.
        """
        try:
            set_public_schema()
            logger.debug("TenantMiddleware.process_response: reset to public")
        except Exception as e:
            logger.error("Failed to reset schema in process_response: %s", e)
        return response

    def process_exception(self, request, exception):
        """
        CRITICAL: Reset schema even when exceptions occur so contaminated
        connections are not returned to the pool.
        """
        try:
            set_public_schema()
            logger.debug(
                "TenantMiddleware.process_exception: reset to public after %s",
                type(exception).__name__,
            )
        except Exception as e:
            logger.critical("Failed to reset schema in process_exception: %s", e)
        return None


_thread_locals = threading.local()

def get_current_request():
    return getattr(_thread_locals, "request", None)


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        _thread_locals.request = request
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request.id
            return response
        finally:
            if hasattr(_thread_locals, "request"):
                del _thread_locals.request
