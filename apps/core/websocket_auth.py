from urllib.parse import parse_qs
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db import close_old_connections
import logging

logger = logging.getLogger(__name__)

class JWTAuthMiddleware:

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        
        close_old_connections()
        
        token = None
        query_string = scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        if "token" in query_params:
            token = query_params["token"][0]
        
        if not token:
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
        
        if token:
            try:
                UntypedToken(token)
                jwt_auth = JWTAuthentication()
                validated_token = jwt_auth.get_validated_token(token)
                user = await self.get_user_from_token(validated_token)
                scope["user"] = user
            except (TokenError, InvalidToken, Exception) as e:
                logger.warning(f"WS Auth Failed: {e}")
                scope["user"] = AnonymousUser()
        else:
            scope["user"] = AnonymousUser()
        
        return await self.inner(scope, receive, send)
    
    async def get_user_from_token(self, validated_token):
        from channels.db import database_sync_to_async
        from apps.core.tenant_utils import with_public_schema
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        @database_sync_to_async
        def get_user():
            def fetch_user():
                user_id = validated_token.get('user_id')
                if not user_id:
                    return AnonymousUser()
                try:
                    return User.objects.select_related('center').get(id=user_id)
                except User.DoesNotExist:
                    return AnonymousUser()
            
            return with_public_schema(fetch_user)
        
        return await get_user()