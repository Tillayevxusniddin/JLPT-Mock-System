# apps/materials/apps.py
from django.apps import AppConfig


class MaterialsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.materials"

    def ready(self):
        import apps.materials.signals  # noqa: F401
