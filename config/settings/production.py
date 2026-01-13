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

# Always ensure localhost is in allowed origins (for local development/testing)
_localhost_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
for origin in _localhost_origins:
    if origin not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(origin)

# Ensure API domain is always in allowed origins (for Swagger UI)
# Convert to list if it's not already
if not isinstance(CORS_ALLOWED_ORIGINS, list):
    CORS_ALLOWED_ORIGINS = list(CORS_ALLOWED_ORIGINS) if CORS_ALLOWED_ORIGINS else []

if "https://api.404online.uz" not in CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS.append("https://api.404online.uz")

# For Swagger UI: Allow same-origin requests (API docs on same domain as API)
CORS_ORIGIN_ALLOW_ALL = False
CORS_ALLOW_CREDENTIALS = True
