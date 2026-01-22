#config/storage.py
from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class StaticStorage(S3Boto3Storage):

    location = 'static'
    default_acl = None
    file_overwrite = True


class MediaStorage(S3Boto3Storage):

    location = 'media'
    default_acl = None
    file_overwrite = False
    querystring_auth = True
    