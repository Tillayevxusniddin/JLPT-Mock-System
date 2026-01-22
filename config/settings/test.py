# config/settings/test.py
from .base import *  # noqa

# ========================================
# Password Hashing (Faster for Tests)
# ========================================

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# ========================================
# API Throttling (Disabled for Tests)
# ========================================

# Disable all throttling for a faster and more stable test suite
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {}

# ========================================
# Celery (Synchronous for Tests)
# ========================================

# Run Celery tasks synchronously in tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ========================================
# Email (Console Backend for Tests)
# ========================================

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ========================================
# Caching (Dummy Cache for Tests)
# ========================================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# ========================================
# Logging (Minimal for Tests)
# ========================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",  # Only show warnings and errors in tests
    },
}