# config/celery.py
import os
from celery import Celery

# Default to production settings as a fail-safe. In development, set
# DJANGO_SETTINGS_MODULE=config.settings.development in your environment.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
