#apps/core/asgi_middleware.py
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
        
        if scope["type"] != "websocket":
            return await self.app(scope, receive, send)

        user = scope.get("user")
        schema_switched = False
        
        if user and user.is_authenticated and getattr(user, "center_id", None):
            try:
                from apps.centers.models import Center
                from asgiref.sync import sync_to_async
                from apps.core.tenant_utils import set_public_schema_async
                await set_public_schema_async()
                
                center = await sync_to_async(Center.objects.get)(id=user.center_id)
                if center.schema_name:
                    await set_tenant_schema_async(center.schema_name)
                    schema_switched = True
                    logger.info(f"✅ WS: Switched to {center.schema_name} for {user.email}")
            
            except Exception as e:
                logger.error(f"❌ WS Schema Switch Error: {e}", exc_info=True)
        
        try:
            return await self.app(scope, receive, send)
        
        finally:
            if schema_switched:
                await reset_tenant_schema_async()
                logger.debug("WS: Schema reset to public")