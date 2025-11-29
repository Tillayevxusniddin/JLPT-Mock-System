from .base import *

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Development-only apps
INSTALLED_APPS += [
    'django_extensions',
]