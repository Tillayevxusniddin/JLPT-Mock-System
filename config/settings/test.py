# config/settings/test.py
from .base import *  # noqa
import os

# ========================================
# Database (Use SQLite for tests)
# ========================================

# Use SQLite for tests to avoid PostgreSQL authentication issues
# SQLite is perfect for testing as it's fast and requires no server
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',  # Use in-memory database for speed
        'CONN_MAX_AGE': 0,
        'ATOMIC_REQUESTS': False,
    }
}

# ========================================
# Migrations (Enable for SQLite tests)
# ========================================

# SQLite tests: enable migrations so Django creates tables from models
# Remove any migration modules disabled in base (from 'from .base import *')
MIGRATION_MODULES = {}  # Empty dict means use default migrations

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

# ========================================
# Middleware Configuration (Tests)
# ========================================

# Disable problematic multi-tenant middleware for tests
# These middleware cause transaction issues in test environment
# Tests run against the public schema, no schema switching needed
MIDDLEWARE = [
    m for m in MIDDLEWARE 
    if 'SchemaResetWrapperMiddleware' not in m
    and 'TenantMiddleware' not in m
]