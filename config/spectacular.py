# config/spectacular.py

def custom_preprocessing_hook(endpoints):
    filtered = []

    for path, path_regex, method, callback in endpoints:

        if path.startswith('/admin/'):
            continue

        if path == '/health/':
            continue

        filtered.append((path, path_regex, method, callback))

    return filtered

def set_schema_for_spectacular():
    """Optional: set tenant schema for OpenAPI schema generation (tenant-scoped examples)."""
    from apps.centers.models import Center
    from apps.core.tenant_utils import set_tenant_schema

    try:
        center = Center.objects.filter(status="ACTIVE").first()
        if center and center.schema_name:
            set_tenant_schema(center.schema_name)
            return center.schema_name
    except Exception:
        pass
    return "public"