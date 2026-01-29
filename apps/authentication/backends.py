# apps/authentication/backends.py
"""
Tenant-aware authentication backend for multi-tenant JLPT system.

- Main domain (e.g. mikan.uz, api.mikan.uz): Only users with center=None (Owner).
- Subdomain (e.g. edu1.mikan.uz): Only users belonging to Center(slug=edu1).

Same email in two centers is isolated by center_id; a user cannot log into
the wrong center because we resolve center from the request host first.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()
logger = logging.getLogger(__name__)


def _get_main_hosts():
    """Main-domain hosts where no center context is applied (Owner login)."""
    return set(
        getattr(
            settings,
            "AUTH_MAIN_DOMAIN_HOSTS",
            ["localhost", "127.0.0.1", "mikan.uz", "www.mikan.uz", "api.mikan.uz"],
        )
    )


class TenantAwareBackend(ModelBackend):
    """
    Subdomain-based authentication. Resolves center from request.get_host()
    so the same email in two centers cannot log into the wrong one.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        center_id = self._get_center_id_from_subdomain(request) if request else None

        try:
            if center_id:
                user = User.objects.get(email=username, center_id=center_id)
            else:
                user = User.objects.get(email=username, center__isnull=True)
        except User.DoesNotExist:
            logger.debug("User not found: email=%s, center_id=%s", username, center_id)
            return None
        except User.MultipleObjectsReturned:
            logger.warning(
                "Multiple users for email=%s, center_id=%s", username, center_id
            )
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
            center_id,
        )
        return user

    def user_can_authenticate(self, user):
        """Reject inactive or soft-deleted users."""
        if not super().user_can_authenticate(user):
            return False
        if getattr(user, "deleted_at", None) is not None:
            return False
        return True

    def _get_center_id_from_subdomain(self, request):
        """Resolve center ID from host. Returns None for main domain."""
        from apps.centers.models import Center

        try:
            host = request.get_host().split(":")[0].lower()
            if host in _get_main_hosts():
                logger.debug("Main domain: %s", host)
                return None

            parts = host.split(".")
            if len(parts) < 3:
                logger.debug("No subdomain: %s", host)
                return None

            subdomain = parts[0]
            center = (
                Center.objects.filter(
                    slug=subdomain,
                    deleted_at__isnull=True,
                )
                .values("id")
                .first()
            )
            if not center:
                logger.warning("No center for subdomain: %s", subdomain)
                return None
            logger.info("Subdomain %s -> center_id=%s", subdomain, center["id"])
            return center["id"]
        except Exception as e:
            logger.exception("Subdomain resolution error: %s", e)
            return None