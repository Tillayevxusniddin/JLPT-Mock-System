# apps/authentication/managers.py
"""
User manager that excludes soft-deleted users from all queries.

- Default manager (User.objects) never returns soft-deleted users, so
  authenticate(), password reset, and any lookup by email/id will not
  see them. Use User.global_objects for admin/analytics if you need
  to include soft-deleted users.
"""
from django.contrib.auth.models import BaseUserManager

from apps.core.managers import SoftDeleteManager, SoftDeleteQuerySet


class SoftDeleteUserManager(BaseUserManager):
    def get_queryset(self):
        base = SoftDeleteQuerySet(self.model, using=self._db)
        return base.filter(deleted_at__isnull=True)

    def _create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The given email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_approved", False)
        return self._create_user(email, password, **extra_fields)
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", "OWNER")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_approved", True)
        return self._create_user(email, password, **extra_fields)

