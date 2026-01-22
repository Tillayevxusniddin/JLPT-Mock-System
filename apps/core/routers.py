# apps/core/routers.py
from django.conf import settings

class TenantRouter:
    def __init__(self):
        self.shared_apps = self._get_app_list('SHARED_APPS')
        self.tenant_apps = self._get_app_list('TENANT_APPS')

    def _get_app_list(self, list_name):
        apps_list = getattr(settings, list_name, [])
        return set([app.split('.')[-1] for app in apps_list]) # Set tezroq ishlaydi

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Connectionni dinamik import qilamiz (circular import oldini olish uchun)
        from django.db import connections
        
        # 'db' argumenti qaysi baza ekanligini aytadi (odatda 'default')
        connection = connections[db]

        if hasattr(connection, 'schema_name'):
            current_schema = connection.schema_name
        elif hasattr(connection, 'get_schema'):
            current_schema = connection.get_schema()
        else:
            current_schema = 'public'

        if current_schema == 'public':
            if app_label in self.shared_apps:
                return True
            if app_label in self.tenant_apps:
                return False
            return None

        # Tenant Schema
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
