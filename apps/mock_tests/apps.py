# apps/mock_tests/apps.py
from django.apps import AppConfig


class MockTestsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mock_tests"
    verbose_name = "Mock Tests"

    def ready(self):
        from . import signals  # noqa: F401
