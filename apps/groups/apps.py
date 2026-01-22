#apps/groups/apps.py
from django.apps import AppConfig


class GroupsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.groups"

    def ready(self):
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
