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

_main_hosts_cache = None


def _get_main_hosts():
    """Main-domain hosts where no center context is applied (Owner login)."""
    global _main_hosts_cache
    if _main_hosts_cache is None:
        _main_hosts_cache = set(
            getattr(
                settings,
                "AUTH_MAIN_DOMAIN_HOSTS",
                ["localhost", "127.0.0.1", "mikan.uz", "www.mikan.uz", "api.mikan.uz"],
            )
        )
    return _main_hosts_cache


def _normalize_host(host):
    """Strip port, lower, and strip whitespace for subdomain resolution."""
    if not host or not isinstance(host, str):
        return ""
    return host.split(":")[0].strip().lower()


class TenantAwareBackend(ModelBackend):
    """
    Email/password authentication for all users regardless of subdomain.
    
    Note: Subdomain validation removed to support centralized login on main domain.
    Tenant context is carried by JWT token after authentication.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)

        try:
            user = User.objects.get(email=username)
        except User.DoesNotExist:
            logger.debug("User not found: email=%s", username)
            return None
        except User.MultipleObjectsReturned:
            # If same email exists in multiple centers, get the first active one
            # Frontend can add center selection UI later if needed
            logger.warning("Multiple users for email=%s, using first active", username)
            user = User.objects.filter(
                email=username,
                is_active=True,
                deleted_at__isnull=True
            ).first()
            if not user:
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

    def _get_center_id_from_subdomain(self, request):
        """
        Resolve center ID from request host. Returns None for main domain.

        Main domain: exact match against AUTH_MAIN_DOMAIN_HOSTS (e.g. localhost,
        api.mikan.uz, www.mikan.uz). Subdomain: host must have at least 3 labels
        (e.g. edu1.mikan.uz); the first label is the center slug. Single-label
        hosts (e.g. "edu1" in dev) are treated as main unless you add a custom
        resolution.
        """
        from apps.centers.models import Center

        try:
            host = _normalize_host(request.get_host() if request else "")
            if not host:
                return None
            if host in _get_main_hosts():
                logger.debug("Main domain: %s", host)
                return None

            parts = [p for p in host.split(".") if p]
            # Require at least 3 labels for subdomain (e.g. edu1.mikan.uz)
            if len(parts) < 3:
                logger.debug("No subdomain (need 3+ labels): %s", host)
                return None

            subdomain = parts[0]
            # Explicitly treat "www" as non-tenant when it's the first label
            # (e.g. www.mikan.uz is in main hosts; www.edu1.mikan.uz would be slug "www")
            if subdomain == "www" and len(parts) >= 3:
                # www.something.tld -> could be main or a center named "www"
                candidate = ".".join(parts[1:])
                if candidate in _get_main_hosts():
                    return None
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