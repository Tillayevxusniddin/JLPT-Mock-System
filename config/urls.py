# config/urls.py
"""
URL configuration. OpenAPI schema is generated with a tenant schema set so
tenant-scoped endpoints are introspected correctly; the schema is always reset
to public afterward.

Custom handler404/handler500 return JSON instead of Django's default HTML so
API clients always receive machine-readable error responses.
"""
import logging

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from apps.core.tenant_utils import set_public_schema
from config.spectacular import set_schema_for_spectacular

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON error handlers (replace Django's default HTML 404/500 pages)
# ---------------------------------------------------------------------------
def custom_404_handler(request, exception=None):
    return JsonResponse(
        {"detail": "The requested resource was not found.", "status_code": 404},
        status=404,
    )


def custom_500_handler(request):
    logger.error("Internal server error at %s", request.path, exc_info=True)
    return JsonResponse(
        {"detail": "An internal server error occurred.", "status_code": 500},
        status=500,
    )


class TenantAwareSpectacularAPIView(SpectacularAPIView):
    """
    Generate OpenAPI schema with a tenant schema active so tenant-scoped models
    (e.g. Group, GroupMembership) are introspected. Always resets to public after.
    """

    def get(self, request, *args, **kwargs):
        set_schema_for_spectacular()
        try:
            return super().get(request, *args, **kwargs)
        finally:
            set_public_schema()

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.v1.urls")),
    path("api/v1/auth/", include(("api.v1.auth_urls", "auth"), namespace="auth")),

    path("api/schema/", csrf_exempt(TenantAwareSpectacularAPIView.as_view()), name="schema"),
    path(
        "api/docs/",
        csrf_exempt(SpectacularSwaggerView.as_view(url_name="schema")),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        csrf_exempt(SpectacularRedocView.as_view(url_name="schema")),
        name="redoc",
    ),
    path("health/", csrf_exempt(lambda r: JsonResponse({"status": "ok"}))),
]

# Django looks for these module-level variables to handle unmatched URLs / crashes.
handler404 = "config.urls.custom_404_handler"
handler500 = "config.urls.custom_500_handler"