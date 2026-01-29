# apps/core/routers.py
"""
Database router for shared-DB, separate-schema multi-tenancy.

- allow_migrate: Ensures shared apps migrate only on public, tenant apps only
  on tenant schemas (schema is set by migrate_tenants command context).
- db_for_read/write: None so all reads/writes use the default DB; schema is
  controlled by search_path (tenant_utils / middleware / auth).
- allow_relation: None. Cross-schema relations (e.g. tenant model holding
  user_id to public User) are handled in application code via with_public_schema;
  no FK across schemas at DB level, so Django relations are not used across
  schema boundaries.
"""
from django.conf import settings


class TenantRouter:
    """Routes migrations by schema; read/write use default DB with search_path."""

    def __init__(self):
        self.shared_apps = self._get_app_list("SHARED_APPS")
        self.tenant_apps = self._get_app_list("TENANT_APPS")

    def _get_app_list(self, list_name):
        apps_list = getattr(settings, list_name, [])
        return set(app.split(".")[-1] for app in apps_list)

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        from django.db import connections

        conn = connections[db]
        if getattr(conn, "schema_name", None) is not None:
            current_schema = conn.schema_name
        elif hasattr(conn, "get_schema"):
            current_schema = conn.get_schema()
        else:
            current_schema = "public"

        if current_schema == "public":
            if app_label in self.shared_apps:
                return True
            if app_label in self.tenant_apps:
                return False
            return None

        if app_label in self.tenant_apps:
            return True
        if app_label in self.shared_apps:
            return False
        return None

    def db_for_read(self, model, **hints):
        return None

    def db_for_write(self, model, **hints):
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None
