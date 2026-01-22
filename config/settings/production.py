#config/settings/production.py
from django.conf.global_settings import SECURE_PROXY_SSL_HEADER
from django.template.defaultfilters import default
import os
from .base import *

# ========================================
# SECURITY SETTINGS
# ========================================

DEBUG = False

if not env("SECRET_KEY", default=None):
    raise ValueError("SECRET_KEY is not set") 

# ========================================
# SSL/HTTPS Configuration
# ========================================

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HTTP Strict Transport Security (HSTS)
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True


# Force HTTPS redirect (can be disabled if Nginx handles it)
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

# ========================================
# Security Headers
# ========================================

# Prevent browsers from detecting content-type
SECURE_CONTENT_TYPE_NOSNIFF = True

# Enable browser XSS protection
SECURE_BROWSER_XSS_FILTER = True

# Prevent site from being framed (clickjacking protection)
# Allow SAMEORIGIN for Swagger UI to work properly
X_FRAME_OPTIONS = "SAMEORIGIN"

# Referrer Policy
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Permissions Policy (formerly Feature-Policy)
PERMISSIONS_POLICY = {
    "geolocation": [],
    "microphone": [],
    "camera": [],
    "payment": [],
    "usb": [],
}


#TODO: barcha cors configurationni korib chiqish
# ========================================
# CORS Configuration
# ========================================

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_METHODS = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
    "HEAD",
]

# Get CORS_ALLOWED_ORIGINS from environment, but ensure localhost is included for development
_cors_origins_from_env = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOWED_ORIGINS = _cors_origins_from_env if _cors_origins_from_env else [
   #TODO: Add production origins
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Ensure CORS_ALLOWED_ORIGINS is a list
if not isinstance(CORS_ALLOWED_ORIGINS, list):
    CORS_ALLOWED_ORIGINS = list(CORS_ALLOWED_ORIGINS) if CORS_ALLOWED_ORIGINS else []
    
# For Swagger UI: Allow same-origin requests (API docs on same domain as API)
CORS_ORIGIN_ALLOW_ALL = False
CORS_ALLOW_CREDENTIALS = True


# Allow all headers for OPTIONS preflight (needed for Swagger UI and frontend)
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "accept-language",
    "authorization",
    "content-type",
    "content-length",
    "dnt",
    "origin",
    "referer",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-center-id",
    "x-forwarded-for",
    "x-forwarded-proto",
    "cache-control",
    "pragma",
]

# Expose headers that Swagger UI might need
CORS_EXPOSE_HEADERS = [
    "content-type",
    "authorization",
    "x-csrftoken",
]

# Preflight cache duration (in seconds)
CORS_PREFLIGHT_MAX_AGE = 86400  # 24 hours
CORS_URLS_REGEX = r'^/(api)/.*$'  

# ========================================
# Cookie Security
# ========================================

#TODO:If needed session based authentication
# SESSION_COOKIE_HTTPONLY = True
# SESSION_COOKIE_SAMESITE = "None"  # Required for cross-origin requests (Netlify frontend)
# SESSION_COOKIE_SECURE = True  # Only send over HTTPS
# SESSION_COOKIE_AGE = 86400  # 24 hours

# CSRF Cookie settings (for cross-origin frontend)
CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript to read CSRF token
CSRF_COOKIE_SAMESITE = "None"  # Required for cross-origin requests
CSRF_COOKIE_SECURE = True  # Only send over HTTPS

# CSRF Trusted Origins (for frontend on Netlify and local development)
_csrf_origins_from_env = env.list("CSRF_TRUSTED_ORIGINS", default=[])
CSRF_TRUSTED_ORIGINS = _csrf_origins_from_env if _csrf_origins_from_env else [
    "https://404online.uz",
    "https://www.404online.uz",
    "https://api.404online.uz",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


# ========================================
# Allowed Hosts
# ========================================

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS", 
    default=[
        #TODO: Add production hosts
        "127.0.0.1",  # For internal Nginx proxy requests
        "localhost",  # For internal requests
    ]
)

if not ALLOWED_HOSTS:
    raise ValueError("ALLOWED_HOSTS environment variable must be set in production")


# ========================================
# Database
# ========================================

# Ensure database connection uses SSL if configured
if env.bool("DB_REQUIRE_SSL", default=True):
    DATABASES["default"]["OPTIONS"] = {
        "sslmode": "require",
    }


# ========================================
# Static and Media Files (AWS S3)
# ========================================

# All static and media files are served from AWS S3 in production
# The USE_S3 flag is checked in base.py settings
# When USE_S3=true, django-storages with S3 backend is used

# Static files collection directory (used during collectstatic)
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# AWS S3 configuration is in base.py and controlled by USE_S3 env variable
# Ensure USE_S3=true in production .env file


# ========================================
# Logging Configuration (JSON format for Loki)
# ========================================

from config.logging_config import JSONFormatter, RequestIDFilter

# Ensure logs directory exists
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": JSONFormatter,
        },
        "verbose": {
            "format": "[{levelname}] {asctime} {name} {module} {funcName} - Schema: {schema_name} - {message}",
            "style": "{",
            "defaults": {"schema_name": "public"},  # Default if not set
        },
        "simple": {
            "format": "[{levelname}] {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "request_id": {
            "()": RequestIDFilter,
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "json",  # Use JSON for Loki
            "filters": ["request_id"],
        },
        "file": {
            "level": "WARNING",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOGS_DIR, "production.log"),
            "maxBytes": 1024 * 1024 * 10,  # 10 MB
            "backupCount": 5,
            "formatter": "json",  # Use JSON for Loki
            "filters": ["request_id"],
        },
        "error_file": {
            "level": "ERROR",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOGS_DIR, "errors.log"),
            "maxBytes": 1024 * 1024 * 10,  # 10 MB
            "backupCount": 10,  # Keep more error logs
            "formatter": "json",
            "filters": ["request_id"],
        },
        # "backup_file": {
        #     "level": "INFO",
        #     "class": "logging.handlers.RotatingFileHandler",
        #     "filename": os.path.join(LOGS_DIR, "backup.log"),
        #     "maxBytes": 1024 * 1024 * 10,  # 10 MB
        #     "backupCount": 5,
        #     "formatter": "verbose",  # Use verbose format for backup logs (more readable)
        #     "delay": False,  # Don't delay file creation
        # },
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
            "filters": ["require_debug_false"],
        },
    },
    "root": {
        "handlers": ["console", "file", "error_file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "error_file", "mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console", "error_file", "mail_admins"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        # Application-specific loggers
        "apps.authentication": {
            "handlers": ["console", "file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.attempts": {
            "handlers": ["console", "file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.assignments": {
            "handlers": ["console", "file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.chat": {
            "handlers": ["console", "file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.notifications": {
            "handlers": ["console", "file", "error_file"],
            "level": "INFO",
            "propagate": False,
        },
        #TODO: Add loggers for other apps -> later

        #TODO: Add loggers for backup operations -> later
        # Backup operations logger
        # "backup": {
        #     "handlers": ["console", "backup_file", "error_file"],
        #     "level": "INFO",
        #     "propagate": False,
        # },
        # Backup management command loggers (catch both logger names)
        # "apps.core.management.commands.backup_db": {
        #     "handlers": ["console", "backup_file", "error_file"],
        #     "level": "INFO",
        #     "propagate": False,
        # },
        # "apps.core.management.commands.restore_db": {
        #     "handlers": ["console", "backup_file", "error_file"],
        #     "level": "INFO",
        #     "propagate": False,
        # },
        # "apps.core.management.commands.cleanup_orphaned_schemas": {
        #     "handlers": ["console", "backup_file", "error_file"],
        #     "level": "INFO",
        #     "propagate": False,
        # },
        # Also catch any logger with "backup" in the name
        # "backup_db": {
        #     "handlers": ["console", "backup_file", "error_file"],
        #     "level": "INFO",
        #     "propagate": False,
        # },
    },
}


# ========================================
# Email Configuration
# ========================================

# Email backend should use SMTP in production
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@nintei-shiken.uz")

ADMIN_NAME = env("ADMIN_NAME", default="Japanese Shiken Admin")
ADMIN_EMAIL = env("ADMIN_EMAIL", default="admin@example.com")
ADMINS = [(ADMIN_NAME, ADMIN_EMAIL)]
# ========================================
# Caching
# ========================================

# Use Redis for caching in production
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "PASSWORD": env("REDIS_PASSWORD", default=None),
        },
        "KEY_PREFIX": "404edu", #TODO: Change key prefix
        "TIMEOUT": 300,
    }
}

# ========================================
# Celery Configuration
# ========================================

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/0")

# ========================================
# Django Axes (Brute Force Protection)
# ========================================

# Already configured in base.py, but ensure it's enabled
AXES_ENABLED = True
AXES_FAILURE_LIMIT = 10
AXES_COOLOFF_TIME = 1  # Hours
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]


# ========================================
# Content Security Policy (Optional but recommended)
# ========================================

# Uncomment and configure if using django-csp
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'")  # Adjust as needed
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")
CSP_IMG_SRC = ("'self'", "data:", "https:")
CSP_FONT_SRC = ("'self'",)
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_ANCESTORS = ("'none'",)