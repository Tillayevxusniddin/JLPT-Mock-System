#apps/centers/apps.py
from django.apps import AppConfig


class CentersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.centers"
    
    def ready(self):
        # Import signals to register them
        from . import signals  # noqa: F401