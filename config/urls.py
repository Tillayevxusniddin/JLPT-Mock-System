# config/urls.py
"""
URL configuration. OpenAPI schema is generated with a tenant schema set so
tenant-scoped endpoints are introspected correctly; the schema is always reset
to public afterward.
"""
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