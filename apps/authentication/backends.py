# apps/authentication/backends.py
"""
Authentication backend for JLPT system.

Email is globally unique across the platform. Users are identified by email
and their center context is carried in the JWT token after authentication.
Subdomain-based tenant resolution is not used; the frontend handles center
routing as a URL prefix while the backend checks the user's center_id.
"""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()
logger = logging.getLogger(__name__)


class TenantAwareBackend(ModelBackend):
    """
    Email/password authentication backend.

    Email is globally unique, so authentication is straightforward.
    Tenant context is carried by the user's center_id after authentication.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)

        try:
            user = User.objects.get(email=username)
        except User.DoesNotExist:
            logger.debug("User not found: email=%s", username)
            return None

        if not user.check_password(password):
            return None
        if not self.user_can_authenticate(user):
            return None
        if getattr(user, "is_deleted", False):
            logger.debug("Rejected soft-deleted user: %s", user.email)
            return None

        logger.info(
            "Authenticated %s (center_id=%s)",
            user.email,
            user.center_id if user.center_id else "None",
        )
        return user

    def user_can_authenticate(self, user):
        """Reject inactive or soft-deleted users."""
        if not super().user_can_authenticate(user):
            return False
        if getattr(user, "deleted_at", None) is not None:
            return False
        return True