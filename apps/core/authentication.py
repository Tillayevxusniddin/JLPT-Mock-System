import logging
from rest_framework_simplejwt.authentication import JWTAuthentication as BaseJWTAuthentication
from apps.core.tenant_utils import set_tenant_schema, set_public_schema, schema_ready

logger = logging.getLogger(__name__)

class TenantAwareJWTAuthentication(BaseJWTAuthentication):

    def authenticate(self, request):

        set_public_schema()
        
        result = super().authenticate(request)

        if result is None:

            logger.debug("TenantAwareJWT: No credentials, staying in public schema")
            request.tenant_schema = "public"
            return None

        user, token = result

        # Log authentication
        logger.info(f"TenantAwareJWT: Authenticated user {user.email} (ID: {user.id})")

        if not user.center_id:
            logger.info(f"TenantAwareJWT: User {user.email} has no center_id, staying in public")
            request.tenant_schema = "public"
            return (user, token)
        
        try:
            from apps.centers.models import Center
            schema_name = Center.objects.values_list('schema_name', flat=True).get(id=user.center_id)
            center_name = Center.objects.values_list('name', flat=True).get(id=user.center_id)
            logger.info(f"TenantAwareJWT: User's center: {center_name}, schema: {schema_name}")

        except Center.DoesNotExist:
            logger.error(f"TenantAwareJWT: Center {user.center_id} does not exist for user {user.email}")
            request.tenant_schema = "public"
            return (user, token)

        try:
            is_ready = Center.objects.values_list('is_ready', flat=True).get(id=user.center_id)
            if not is_ready:
                from rest_framework.exceptions import AuthenticationFailed
                logger.warning(f"TenantAwareJWT: Center {center_name} not ready (is_ready=False)")
                raise AuthenticationFailed({
                    'error': 'CENTER_NOT_READY',
                    'message': 'Your center is still being initialized. Please try again in a few moments.',
                    'center_name': center_name,
                    'retry_after': 10  # seconds
                })
        except Exception as e:
            if 'is_ready' in str(e).lower() or 'column' in str(e).lower():
                logger.debug(f"TenantAwareJWT: is_ready column not found, assuming center is ready (backward compatibility)")
            else:
                raise
        
        if not schema_ready(schema_name):
            from rest_framework.exceptions import AuthenticationFailed
            logger.warning(f"TenantAwareJWT: Schema {schema_name} not ready (tables missing)!")
            raise AuthenticationFailed({
                'error': 'SCHEMA_NOT_READY',
                'message': 'Your center is still being initialized. Please try again in a few moments.',
                'center_name': center_name,
                'retry_after': 10
            })

        try:
            set_tenant_schema(schema_name)
            request.tenant_schema = schema_name
            logger.info(f"TenantAwareJWT: ✅ Switched to schema: {schema_name}")
        except Exception as e:
            logger.error(f"TenantAwareJWT: Failed to switch to {schema_name}: {e}", exc_info=True)
            set_public_schema()
            request.tenant_schema = "public"
        return (user, token)

        
            
        




