from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView
    SpectacularRedocView,
)
from django.db import connection

class TenantAwareSpectacularAPIView(SpectacularAPIView):
    def get(self, request, *args, **kwargs):
        from apps.organizations.models import Organization
        try:
            organization = Organization.objects.filter(status='ACTIVE').first()
            if organization:
                connection.set_tenant(organization)
        except Exception:
            pass
        return super().get(request, *args, **kwargs)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.v1.urls")),
     # Swagger UI - Interactive API documentation
    path(
        "api/docs/",
        csrf_exempt(SpectacularSwaggerView.as_view(url_name="schema")),
        name="swagger-ui",
    ),
    # ReDoc - Alternative clean documentation UI
    path(
        "api/redoc/",
        csrf_exempt(SpectacularRedocView.as_view(url_name="schema")),
        name="redoc",
    ),
    path("health/", csrf_exempt(lambda r: JsonResponse({"status": "ok"}))),
]