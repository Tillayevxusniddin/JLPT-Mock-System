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

    @staticmethod
    def _get_app_list(list_name):
        """Extract Django app_labels from SHARED_APPS / TENANT_APPS.

        Handles both dotted module paths ('apps.groups') and AppConfig
        references ('apps.mock_tests.apps.MockTestsConfig').  In both
        cases the resolved app_label is the second-to-last segment for
        'apps.X' paths, or the last segment for plain module names.
        """
        from django.apps import apps as django_apps

        apps_list = getattr(settings, list_name, [])
        labels = set()
        for entry in apps_list:
            # Try resolving via Django's app registry first (handles AppConfig).
            try:
                config = django_apps.get_app_config(
                    entry.rsplit(".", 1)[0].split(".")[-1]
                    if ".apps." in entry
                    else entry.split(".")[-1]
                )
                labels.add(config.label)
                continue
            except LookupError:
                pass
            # Fallback: for 'apps.foo.apps.FooConfig' → 'foo',
            # for 'apps.foo' → 'foo', for 'django.contrib.auth' → 'auth'.
            parts = entry.split(".")
            if ".apps." in entry and len(parts) >= 3:
                # e.g. 'apps.mock_tests.apps.MockTestsConfig' → 'mock_tests'
                labels.add(parts[-3])
            else:
                labels.add(parts[-1])
        return labels

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
