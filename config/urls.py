from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from apps.core.tenant_utils import set_tenant_schema

#TODO: If I gonna to create tenant-aware schema, I need to set the tenant
class TenantAwareSpectacularAPIView(SpectacularAPIView):
    def get(self, request, *args, **kwargs):
        try:
            from apps.centers.models import Center
            center = Center.objects.filter(is_active=True).exclude(schema_name__isnull=True).first()
            if center and center.schema_name:
                set_tenant_schema(center.schema_name)
        except Exception:
            pass
            
        return super().get(request, *args, **kwargs)

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