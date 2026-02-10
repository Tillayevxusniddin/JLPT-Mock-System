# apps/core/websocket_auth.py
"""
JWT authentication middleware for Django Channels WebSocket connections.

Extracts the token from query string (?token=<jwt>) or Authorization header
(Bearer <jwt>), validates once via JWTAuthentication, and attaches the user
to scope["user"]. Invalid/missing tokens result in AnonymousUser so the
consumer can reject with a 4401 close code.
"""
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

logger = logging.getLogger(__name__)


class JWTAuthMiddleware:
    """ASGI middleware: authenticate WebSocket via JWT, attach user to scope."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Close stale DB connections (must be async-safe).
        await database_sync_to_async(close_old_connections)()

        token = self._extract_token(scope)

        if token:
            try:
                # Single validation pass — get_validated_token already verifies
                # signature, expiry, and token type. No need for UntypedToken.
                jwt_auth = JWTAuthentication()
                validated_token = jwt_auth.get_validated_token(token)
                user = await self._get_user_from_token(validated_token)
                scope["user"] = user
            except (TokenError, InvalidToken) as e:
                logger.warning("WS Auth: token rejected: %s", e)
                scope["user"] = AnonymousUser()
            except Exception as e:
                # Unexpected error (DB down, coding bug) — log at error level.
                logger.error("WS Auth: unexpected error during authentication: %s", e, exc_info=True)
                scope["user"] = AnonymousUser()
        else:
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)

    @staticmethod
    def _extract_token(scope):
        """Extract JWT from query string (?token=...) or Authorization header."""
        # 1) Query string: ws://host/ws/notifications/?token=<jwt>
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        if "token" in query_params:
            return query_params["token"][0]

        # 2) Header: Authorization: Bearer <jwt>
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()
        if auth_header.startswith("Bearer "):
            return auth_header.split(" ", 1)[1]

        return None

    @staticmethod
    async def _get_user_from_token(validated_token):
        """Fetch user from public schema using the validated JWT payload."""
        from apps.core.tenant_utils import with_public_schema
        from django.contrib.auth import get_user_model

        User = get_user_model()

        @database_sync_to_async
        def get_user():
            def fetch_user():
                user_id = validated_token.get("user_id")
                if not user_id:
                    return AnonymousUser()
                try:
                    return User.objects.select_related("center").get(id=user_id)
                except User.DoesNotExist:
                    return AnonymousUser()

            return with_public_schema(fetch_user)

        return await get_user()