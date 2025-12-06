import logging
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from apps.core.tenant_utils import set_tenant_schema, set_public_schema, get_current_schema, schema_exists

logger = logging.getLogger(__name__)

class TenantMiddleware(MiddlewareMixin):
    """
    Middleware to handle tenant schema switching.
    CRITICAL: Always resets to public schema after request to prevent schema pollution.
    """
    
    def process_request(self, request):
        """Set tenant schema based on authenticated user's organization"""
        # Store original schema for debugging
        request._original_schema = get_current_schema()
        
        if request.user.is_authenticated and request.user.organization:
            schema_name = request.user.organization.schema_name
            
            # Validate schema exists before switching
            if not schema_exists(schema_name):
                logger.error(
                    f"Schema {schema_name} does not exist for organization {request.user.organization.id}. "
                    f"Organization may not be properly initialized."
                )
                set_public_schema()
                return JsonResponse({
                    'error': 'Organization not initialized',
                    'detail': 'Your organization is being set up. Please try again in a few moments or contact support.'
                }, status=503)
            
            try:
                set_tenant_schema(schema_name)
                request.tenant_schema = schema_name
                logger.debug(f"Switched to tenant schema: {schema_name}")
            except Exception as e:
                logger.error(f"Failed to set tenant schema {schema_name}: {e}")
                set_public_schema()
                request.tenant_schema = "public"
                return JsonResponse({
                    'error': 'Service temporarily unavailable',
                    'detail': 'Unable to access organization data. Please try again.'
                }, status=503)
        else:
            set_public_schema()
            request.tenant_schema = "public"

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