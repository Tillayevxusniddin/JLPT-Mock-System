#config/settings/base.py
from pathlib import Path
from datetime import timedelta
import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default='default-secret-key$$')
DEBUG = env.bool("DJANGO_DEBUG", default=True)

# Multi-tenancy: the frontend uses center slugs as URL prefixes (e.g.
# edu1.mikan.uz) for branding; auth is centralized on the main domain.
# '.mikan.uz' allows all subdomains so Django accepts requests regardless.
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=[
        ".mikan.uz",   # Wildcard for all center slug prefixes
        "mikan.uz",    # Main domain
        "localhost",   # Development
        "127.0.0.1",
        "[::1]",
    ],
)



SHARED_APPS = [
    #django core apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',

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
    "apps.centers",
]

TENANT_APPS = [
    # Django core apps (needed in tenant schemas for migrations)
    "django.contrib.contenttypes",
    "django.contrib.auth",

    # Business logic apps (TENANT schema - isolated per organizations)
    "apps.groups",
    "apps.materials",
    "apps.mock_tests.apps.MockTestsConfig",
    "apps.assignments",
    "apps.attempts",
    "apps.notifications",
    "apps.chat",
    "apps.analytics",
]

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

MIDDLEWARE = [
    "apps.core.middleware.SchemaResetWrapperMiddleware",
    "apps.core.middleware.RequestLogMiddleware",
    "django.middleware.security.SecurityMiddleware",
    'corsheaders.middleware.CorsMiddleware',  # CORS must be before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # TenantMiddleware removed: SchemaResetWrapperMiddleware (position 0) already
    # resets search_path to public in both __call__ entry AND finally block,
    # making the triple-reset in TenantMiddleware redundant (saves ~3 DB
    # round-trips per request).
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

DATABASE_ROUTERS = ["apps.core.routers.TenantRouter"]
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

# Celery Beat Schedule for periodic tasks
CELERY_BEAT_SCHEDULE = {
    'check-expired-subscriptions-daily': {
        'task': 'apps.centers.tasks.check_and_suspend_expired_subscriptions',
        'schedule': 86400.0,  # Run every 24 hours (in seconds)
        # Alternatively, use crontab for specific times:
        # 'schedule': crontab(hour=2, minute=0),  # Run at 2 AM daily
    },
    'auto-submit-stuck-submissions': {
        'task': 'apps.attempts.tasks.auto_submit_stuck_submissions',
        'schedule': 300.0,  # Run every 5 minutes
    },
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
    
    # Custom domain (optional - for CDN). When set, static/media URLs use this domain.
    # Ensure bucket CORS allows origins: api.mikan.uz and frontend origins.
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
    # "x-organization-id",  # DEPRECATED: Removed; tenant is identified via user's center_id in JWT
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
    "apps.authentication.backends.TenantAwareBackend",
    "axes.backends.AxesBackend",  # django-axes backend (wraps ModelBackend)
    "django.contrib.auth.backends.ModelBackend",  # default
]

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),  # 1 day for development
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),     # 7 days
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.core.authentication.TenantAwareJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'apps.core.pagination.DefaultPagination', # O'zingiz yozgan paginationni ulang
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
    
    # Throttling
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour', 
        'user': '1000/hour', 
        'auth': '10/minute', 
        'password_reset': '5/hour',
        'uploads': '1000/hour',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# ---------------------------------------------------------------------------
# drf-spectacular – OpenAPI 3.0 schema generation
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    # ── API metadata ──────────────────────────────────────────────────────
    "TITLE": "Mikan – JLPT Mock Exam Platform API",
    "DESCRIPTION": (
        "Multi-tenant SaaS platform for Japanese Language Proficiency Test (JLPT) "
        "preparation. Manage language centers, teachers, students, mock exams, "
        "quizzes, homework assignments, and analytics.\n\n"
        "## Authentication\n"
        "All endpoints (except **Public – Contact** and **Authentication** login/register) "
        "require a JWT bearer token. Obtain tokens via `POST /api/v1/auth/login/` and "
        "include the **access** token in the `Authorization: Bearer <token>` header.\n\n"
        "## Multi-Tenancy\n"
        "Each language center is an isolated tenant. The JWT token automatically "
        "switches the database schema to the user's center context.\n\n"
        "## Roles\n"
        "| Role | Description |\n"
        "|------|-------------|\n"
        "| **OWNER** | Platform super-admin – manages all centers |\n"
        "| **CENTER_ADMIN** | Administers a single center |\n"
        "| **TEACHER** | Creates exams, quizzes, assigns homework |\n"
        "| **STUDENT** | Takes exams and views results |\n"
        "| **GUEST** | Limited read-only access (pre-enrollment) |\n"
    ),
    "VERSION": "1.0.0",
    "CONTACT": {
        "name": "Mikan API Support",
        "email": "admin@mikan.uz",
        "url": "https://mikan.uz",
    },
    "LICENSE": {
        "name": "Proprietary",
    },
    "TERMS_OF_SERVICE": "https://mikan.uz/terms/",

    # ── Server URLs (Swagger 'Servers' dropdown) ─────────────────────────
    "SERVERS": [
        {"url": "http://localhost:8000", "description": "Local development"},
        {"url": "https://api.mikan.uz", "description": "Production"},
    ],

    # ── Security (JWT) ───────────────────────────────────────────────────
    "SECURITY": [{"jwtAuth": []}],

    # ── Preprocessing ────────────────────────────────────────────────────
    "PREPROCESSING_HOOKS": ["config.spectacular.custom_preprocessing_hook"],

    # ── Tag ordering (matches Swagger UI sidebar) ────────────────────────
    "TAGS": [
        {"name": "Authentication", "description": "Register, login, logout, password management, and avatar upload."},
        {"name": "Users", "description": "User CRUD for CENTER_ADMIN and TEACHER roles."},
        {"name": "Owner – Centers / Admins / Requests", "description": "Platform owner (super-admin) endpoints for center and subscription management."},
        {"name": "Center Admin – Invitations / Profile / Guests", "description": "Center administrator endpoints for invitations, profile, and guest management."},
        {"name": "Public – Contact", "description": "Unauthenticated endpoints for the public landing page."},
        {"name": "Groups", "description": "Student groups within a center."},
        {"name": "Group Memberships", "description": "Add/remove students from groups."},
        {"name": "Materials", "description": "Supplementary learning materials (documents, audio, images)."},
        {"name": "Mock Tests", "description": "Full JLPT mock exams."},
        {"name": "Test Sections", "description": "Sections within a mock test (Vocabulary, Reading, Listening)."},
        {"name": "Question Groups (Mondai)", "description": "Question groups (問題) within test sections."},
        {"name": "Questions", "description": "Individual questions within question groups."},
        {"name": "Quizzes", "description": "Standalone quizzes for practice."},
        {"name": "Quiz Questions", "description": "Questions within quizzes."},
        {"name": "Exam Assignments", "description": "Assign mock exams to student groups."},
        {"name": "Homework Assignments", "description": "Assign homework (quizzes + mock tests) to groups."},
        {"name": "Submissions", "description": "Student exam/homework submissions and results."},
        {"name": "Submissions – Exam", "description": "Exam-specific submission flows (start, submit, results)."},
        {"name": "Submissions – Homework", "description": "Homework-specific submission flows."},
        {"name": "Notifications", "description": "In-app notification management."},
        {"name": "Analytics – Owner", "description": "Platform-wide analytics for the owner."},
        {"name": "Analytics – Center Admin", "description": "Center-level analytics for administrators."},
        {"name": "Analytics – Teacher", "description": "Teacher performance and class analytics."},
        {"name": "Analytics – Student", "description": "Student progress and score analytics."},
    ],

    # ── Enum collision overrides ─────────────────────────────────────────
    "ENUM_NAME_OVERRIDES": {
        "ExamRoomStatusEnum": "apps.assignments.models.ExamAssignment.RoomStatus",
        "SubmissionStatusEnum": "apps.attempts.models.Submission.Status",
        "CenterStatusEnum": "apps.centers.models.Center.Status",
        "MockTestStatusEnum": "apps.mock_tests.models.MockTest.Status",
        "UserRoleEnum": "apps.authentication.models.User.Role",
        "InvitationStatusEnum": "apps.centers.models.Invitation.STATUS_CHOICES",
        "InvitationRoleEnum": "apps.centers.models.Invitation.ROLE_CHOICES",
        "ContactRequestStatusEnum": "apps.centers.models.ContactRequest.STATUS_CHOICES",
    },

    # ── Schema behaviour ─────────────────────────────────────────────────
    "SCHEMA_PATH_PREFIX": "/api/v[0-9]+",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": False,
        "filter": True,
        "docExpansion": "list",
        "defaultModelsExpandDepth": -1,
        "tagsSorter": "alpha",
    },
    "SWAGGER_UI_FAVICON_HREF": "/static/images/favicon-32x32.png",
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
