import logging
from apps.core.tenant_utils import (
    set_tenant_schema_async, 
    reset_tenant_schema_async
)

logger = logging.getLogger(__name__)

class TenantASGIMiddleware:
    def __init__(self, app):
        self.app = app

        async def __call__(self, scope, receive, send):
            if scope['type'] == 'websocket':
                user = scope.get('user', None)
                logger.debug(f"WebSocket connection attempt - Path: {scope.get('path')}")
                logger.debug(f"User: {user if not user else getattr(user, 'email', 'Unknown')}, Authenticated: {getattr(user, 'is_authenticated', False)}")

                if user and hasattr(user, "is_authenticated") and user.is_authenticated:
                    logger.debug(f"User {user.email} is authenticated")
                    if hasattr(user, "center_id") and user.center_id:
                        from apps.core.tenant_utils import set_public_schema_async
                        from apps.centers.models import Center
                        from asgiref.sync import sync_to_async

                        await set_public_schema_async()
                        try:
                            center = await sync_to_async(Center.objects.get)(id=user.center_id)
                            schema_name = center.schema_name
                            logger.info(f"User {user.email} has center: {center.name}, schema: {schema_name}")
                        except Center.DoesNotExist:
                            logger.warning(f"Center {user.center_id} does not exist")
                            schema_name = None

                        if schema_name:
                            try:
                                await set_tenant_schema_async(schema_name)
                                logger.info(
                                    f"✅ WebSocket: Switched to schema {schema_name} for user {user.email}"
                                )
                            except Exception as e:
                                logger.error(
                                    f"❌ Failed to switch schema for WebSocket: {str(e)}",
                                    exc_info=True,
                                    extra={
                                        'user_id': user.id,
                                        'schema_name': schema_name,
                                        'path': scope.get('path')
                                    }
                                )
                        else:
                            logger.warning(
                                f"User {user.email} has center but no schema_name. "
                                f"WebSocket will use public schema."
                            )
                    else:
                        logger.info(
                            f"User {user.email} has no center. "
                            f"WebSocket will use public schema."
                        )
                            
                else:
                    logger.warning(f"❌ Unauthenticated WebSocket connection attempt - Path: {scope.get('path')}")

            try:
                return await self.app(scope, receive, send)

            finally:
                if scope["type"] == "websocket":
                    await reset_tenant_schema_async()
                    logger.debug("WebSocket connection closed, schema reset to public")
                