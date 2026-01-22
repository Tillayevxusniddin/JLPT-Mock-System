#apps/core/middleware.py
import logging
from django.utils.deprecation import MiddlewareMixin
from apps.core.tenant_utils import set_public_schema, get_current_schema
import threading
import uuid

logger = logging.getLogger(__name__)

class TenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        """
        DEPRECATED: Schema switching now handled by TenantAwareJWTAuthentication.
        """
        current_schema = get_current_schema()
        logger.debug(f"TenantMiddleware.process_request: Current schema={current_schema}, path={request.path}")

        return None

    def process_response(self, request, response):
        """
        CRITICAL: Always reset to public schema after request.
        This prevents schema pollution in connection pools.
        """
        try:
            set_public_schema()
            logger.debug("Reset to public schema after request")
        except Exception as e:
            logger.error(f"Failed to reset schema in process_response: {e}")
        return response

    def process_exception(self, request, exception):
        """
        CRITICAL: Reset schema even when exceptions occur.
        Prevents contaminated connections from being returned to pool.
        """
        try:
            set_public_schema()
            logger.error(f"Reset to public schema after exception: {exception}")
        except Exception as e:
            logger.critical(f"Failed to reset schema in process_exception: {e}")
        return None

    

_thread_locals = threading.local()

def get_current_request():
    return getattr(_thread_locals, 'request', None)

class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        _thread_locals.request = request
        try:
            response = self.get_response(request)
            response['X-Request-ID'] = request.id
            return response
        finally:
            if hasattr(_thread_locals, 'request'):
            del _thread_locals.request
        return response

        
        
        
        
        
        
            
        

        