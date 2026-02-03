# config/spectacular.py
"""
drf-spectacular OpenAPI schema configuration for multi-tenant JLPT system.

- custom_preprocessing_hook: Excludes admin and health from the schema.
- set_schema_for_spectacular: Switches to a tenant schema during schema generation so
  tenant-scoped models (e.g. Group, GroupMembership) are introspected correctly.
  Call from TenantAwareSpectacularAPIView; always pair with set_public_schema() in a
  finally block so the connection is reset after generation.
"""

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
    """
    Set the DB connection to a tenant schema for OpenAPI schema generation.
    Use when generating the schema so tenant-scoped serializers/models are
    introspected in a real tenant context. Returns the schema name set, or "public".

    Caller must reset to public in a finally block (e.g. set_public_schema()).
    """
    from apps.centers.models import Center
    from apps.core.tenant_utils import set_tenant_schema

    try:
        center = (
            Center.objects.filter(is_active=True)
            .exclude(schema_name__isnull=True)
            .exclude(schema_name="")
            .first()
        )
        if center and center.schema_name:
            set_tenant_schema(center.schema_name)
            return center.schema_name
    except Exception:
        pass
    return "public"