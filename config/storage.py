# config/storage.py
"""
S3-compatible storage for Multi-Tenant JLPT.

- StaticStorage: public static assets (no signed URLs).
- MediaStorage: default media; uses querystring_auth (signed URLs) for private access.
- PrivateMediaStorage: for sensitive exam materials (audio/images); always signed,
  optional short expiry. Use for MockTest/Quiz media if you want time-limited URLs.
"""
from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class StaticStorage(S3Boto3Storage):
    """Public static files (CSS, JS). No signed URLs."""
    location = "static"
    default_acl = None
    file_overwrite = True
    querystring_auth = False


class MediaStorage(S3Boto3Storage):
    """
    Default media (avatars, materials, mock test media).
    querystring_auth=True: generated URLs are signed so private buckets work.
    """
    location = "media"
    default_acl = None
    file_overwrite = False
    querystring_auth = True


class PrivateMediaStorage(S3Boto3Storage):
    """
    Sensitive exam materials (e.g. listening audio, question images).
    Always signed URLs; short-lived via AWS_SENSITIVE_MEDIA_EXPIRE (default 3600s).
    """
    location = "media"
    default_acl = None
    file_overwrite = False
    querystring_auth = True

    @property
    def querystring_expire(self):
        return getattr(settings, "AWS_SENSITIVE_MEDIA_EXPIRE", 3600)
