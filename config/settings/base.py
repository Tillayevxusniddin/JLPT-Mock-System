from pathlib import Path
from datetime import timedelta
import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default='django-insecure-a0rqa6awp2dl)nsmo&_bhc!-6n#zzpazly$p9+mg)d3f0fs4w+')
DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])


SHARED_APPS = [
    #django core apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # third party apps
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "channels",
    "corsheaders",
    "rest_framework_simplejwt.token_blacklist",
    "axes",  
    "storages",

    # local shared apps (PUBLIC schema)
    "apps.core",
    "apps.authentication",
    "apps.organizations",
    "apps.invitations",
    "apps.notifications",
    "apps.audit"

]

TENANT_APPS = [
    # Django core apps (needed in tenant schemas for migrations)
    "django.contrib.contenttypes",
    "django.contrib.auth",

    # Business logic apps (TENANT schema - isolated per organizations)

    "apps.groups",
    "apps.materials",
    "apps.mock_tests",
    "apps.materials",
    "apps.assignments",
    "apps.attempts",
    "apps.chat",
    "apps.analytics"
]

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # CORS must be before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.TenantMiddleware',
    "axes.middleware.AxesMiddleware",

]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [str(BASE_DIR / "templates")],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME', default='jlpt_mock_db'),
        'USER': env('DB_USER', default='postgres'),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='5432'),
        'OPTIONS':{
            'options': '-c search_path=public'
        },
        'CONN_MAX_AGE': 600,
    }
}

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True


CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("REDIS_URL", default="redis://localhost:6379/0")]},
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=env("REDIS_URL", default="redis://localhost:6379/0"))
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_TIMEZONE = TIME_ZONE

#TODO: Add tasks to the schedule
CELERY_BEAT_SCHEDULE={}

#TODO: Configure Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.core.authentication.TenantAwareJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%S.%fZ',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',  # Anonymous users: 100 requests per hour
        'user': '1000/hour',  # Authenticated users: 1000 requests per hour
        'auth': '10/minute',  # Login/register: 10 attempts per minute
        'password_reset': '5/hour',  # Password reset: 5 attempts per hour
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',  # API documentation
}


DATA_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100MB

USE_S3 = env.bool("USE_S3", default=False)

if USE_S3:
    # S3-Compatible Storage (Minio/VDS/AWS S3)
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="404edu-media")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")
    
    # S3-compatible endpoint (required for Minio/VDS)
    # Minio: http://your-server:9000 or https://minio.yourdomain.com
    # VDS: https://storage.vdsina.ru or your VDS endpoint
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default=None)
    
    # Custom domain (optional - for CDN)
    # Leave empty for direct S3 URLs
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default=None)
    
    # Security & Performance
    # IMPORTANT: ACL must be None for buckets with "ACLs disabled" (AWS default since 2023)
    # Read from env, but convert empty string to None
    aws_default_acl = env("AWS_DEFAULT_ACL", default=None)
    AWS_DEFAULT_ACL = None if aws_default_acl in (None, "", "None", "none") else aws_default_acl
    
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = True
    AWS_S3_VERIFY = env.bool("AWS_S3_VERIFY_SSL", default=True)  # Set false for self-signed certs
    
    # Storage backends
    STORAGES = {
        "default": {"BACKEND": "config.storage.MediaStorage"},
        "staticfiles": {"BACKEND": "config.storage.StaticStorage"},
    }
    
    # URLs
    MEDIA_URL = f"/media/"
    if AWS_S3_CUSTOM_DOMAIN:
        STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/static/"
    else:
        # Direct S3/Minio URLs
        STATIC_URL = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/static/"
else:
    # Local file storage (development)
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"
    STATIC_URL = "/static/"
    STATIC_ROOT = BASE_DIR / "staticfiles"
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATICFILES_DIRS = []

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-organization-id",
]

# Email Configuration (SMTP) or (SES)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@nintei-shiken.com")


FRONTEND_URL_BASE = env("FRONTEND_URL_BASE", default="http://localhost:3000")

AUTH_USER_MODEL = 'authentication.User'
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesBackend",  # django-axes backend (wraps ModelBackend)
    "django.contrib.auth.backends.ModelBackend",  # default
]

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),  # 1 day for development
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),     # 7 days
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# DRF throttling: 
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = [
    "rest_framework.throttling.ScopedRateThrottle",
]
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "auth": "10/minute",  # Login/register: 10 requests per minute
    "uploads": "1000/hour",  # Content creation with uploads: 1000 per hour (increased for bulk question/group creation workflow)
    #"questions": "500/minute",  # Question CRUD operations: 500 per minute (allows creating 40 questions with frequent GET requests for state updates)
}

#TODO: need to consider
GUEST_ALLOWED_VIEWS = [
    """
    view name
    """
]

if not DEBUG:
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
        "rest_framework.renderers.JSONRenderer",
    ]


AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=10)
AXES_COOLOFF_TIME = env.int("AXES_COOLOFF_TIME", default=1)
AXES_LOCKOUT_PARAMETERS = [["email", "ip_address"]]
AXES_USERNAME_FORM_FIELD = "email"
AXES_LOCKOUT_TEMPLATE = None
AXES_RESET_ON_SUCCESS = True
AXES_ENABLED = True
AXES_CACHE = "default"
AXES_VERBOSE = DEBUG
AXES_LOCK_OUT_AT_FAILURE = True


# DRF Spectacular (API Documentation)
SPECTACULAR_SETTINGS = {
    'TITLE': 'JLPT Mock System API',
    'DESCRIPTION': 'Multi-tenant JLPT Mock Test Management System',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/',
}


#TODO: Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(BASE_DIR / 'logs' / 'django.log'),
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'security_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(BASE_DIR / 'logs' / 'security.log'),
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['security_file', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}



CHAT_MAX_ATTACHMENT_FILES = env.int("CHAT_MAX_ATTACHMENT_FILES", default=10)
CHAT_MAX_ATTACHMENT_SIZE_MB = env.int("CHAT_MAX_ATTACHMENT_SIZE_MB", default=10)

#TODO: Spectacular Settings
SPECTACULAR_SETTINGS = {

}

