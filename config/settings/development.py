#config/settings/development.py
from .base import * # noqa

DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

CORS_ALLOWED_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
