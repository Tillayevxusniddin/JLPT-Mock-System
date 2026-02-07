# config/settings/test.py
from .base import *  # noqa
import os

# ========================================
# Database (Use PostgreSQL for tests)
# ========================================

# Use PostgreSQL for tests to avoid compatibility issues with SQLite
# Tests run against a separate test database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'jlpt_mock_db') + '_test',
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'postgres'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'OPTIONS': {
            'options': '-c search_path=public'
        },
        'CONN_MAX_AGE': 0,  # Disable connection pooling in tests
        'ATOMIC_REQUESTS': True,  # Wrap each test in a transaction
    }
}

# ========================================
# Migrations (Disable for tests)
# ========================================

class DisableMigrations:
    """Disable migrations for tests to speed them up."""
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()

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

# ========================================
# Django Axes (Disable for Tests)
# ========================================

AXES_ENABLED = False

# ========================================
# Authentication Backends (Test)
# ========================================

AUTHENTICATION_BACKENDS = [
    "apps.authentication.backends.TenantAwareBackend",
]

# Skip schema readiness check in tests (tenant tables not migrated)
SKIP_SCHEMA_READY_CHECK = True

# Propagate exceptions for clearer test failures
DEBUG_PROPAGATE_EXCEPTIONS = True