"""
ASGI config for 404-edu project with schema-based multi-tenancy support.

This module configures both HTTP and WebSocket protocols with proper schema isolation:
- HTTP: Handled by Django's ASGI application
- WebSocket: Wrapped with TenantASGIMiddleware for schema switching

Flow:
    ProtocolTypeRouter
    ├── HTTP → Django ASGI Application
    └── WebSocket → TenantASGIMiddleware
                    └── JWTAuthMiddlewareStack
                        └── URLRouter (chat, notifications, exam routes)
"""


import os 
from django.core.asgi import get_asgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings"
)

django_asgi_app = get_asgi_application()

try:
    from channels.routing import ProtocolTypeRouter, URLRouter
    from apps.core.websocket_auth import JWTAuthMiddleware
    from apps.core.asgi_middleware import TenantASGIMiddleware
    from apps.chat.routing import websocket_urlpatterns as chat_patterns
    from apps.notifications.routing import websocket_urlpatterns as notify_patterns



    combined_patterns = chat_patterns + notify_patterns


    application = ProtocolTypeRouter({
        "http":django_asgi_app,
        "websocket":JWTAuthMiddleware(
            TenantASGIMiddleware(
                URLRouter(combined_patterns)
            )
        ),
    })

except ImportError as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to import WebSocket routing: {str(e)}", exc_info=True)
    application = django_asgi_app
except Exception as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to configure WebSocket routing: {str(e)}", exc_info=True)
    application = django_asgi_app