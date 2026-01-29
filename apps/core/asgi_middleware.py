# apps/core/asgi_middleware.py
"""
ASGI middleware that sets the DB search_path for WebSocket connections based on
the authenticated user's center.

Caveat (CONN_MAX_AGE > 0): sync_to_async runs in a thread pool; each call may
use a different connection. So the schema set here might not apply to the next
DB call in the consumer. For reliable per-message schema isolation, wrap each
consumer method's DB work in database_sync_to_async(lambda: (set_tenant_schema(s); do_work())).
"""
import logging

from asgiref.sync import sync_to_async

from apps.core.tenant_utils import (
    set_public_schema_async,
    set_tenant_schema_async,
    reset_tenant_schema_async,
)

logger = logging.getLogger(__name__)


class TenantASGIMiddleware:
    """Set tenant schema for WebSocket scope based on scope['user'].center_id."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            return await self.app(scope, receive, send)

        user = scope.get("user")
        schema_switched = False

        center_id = getattr(user, "center_id", None) if user else None
        if user and getattr(user, "is_authenticated", False) and center_id:
            try:
                await set_public_schema_async()
                from apps.centers.models import Center

                def _get_center(cid):
                    return Center.objects.only("id", "schema_name").get(id=cid)

                center = await sync_to_async(_get_center)(center_id)
                if center and getattr(center, "schema_name", None):
                    await set_tenant_schema_async(center.schema_name)
                    schema_switched = True
                    logger.info(
                        "WS: Switched to schema %s for user %s",
                        center.schema_name,
                        getattr(user, "email", user.pk),
                    )
            except Exception as e:
                logger.exception("WS schema switch error: %s", e)

        try:
            return await self.app(scope, receive, send)
        finally:
            if schema_switched:
                await reset_tenant_schema_async()
                logger.debug("WS: Schema reset to public")