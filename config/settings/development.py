#config/settings/development.py
from .base import *  # noqa

DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# In development we typically allow all origins (see CORS_ALLOW_ALL_ORIGINS in base.py).
# If you want to restrict, set CORS_ALLOWED_ORIGINS as a list in .env.
