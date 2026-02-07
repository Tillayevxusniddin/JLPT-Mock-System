# apps/core/authentication.py
"""
JWT authentication that switches the database search_path to the authenticated
user's tenant schema. Must run after TenantMiddleware has reset to public.
"""
import logging

from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import (
    JWTAuthentication as BaseJWTAuthentication,
)

from apps.core.tenant_utils import (
    set_tenant_schema,
    set_public_schema,
    schema_ready,
)

logger = logging.getLogger(__name__)


class TenantAwareJWTAuthentication(BaseJWTAuthentication):
    """Authenticate via JWT and set request DB schema to the user's center schema."""

    def authenticate(self, request):
        set_public_schema()
        result = super().authenticate(request)

        if result is None:
            request.tenant_schema = "public"
            logger.debug("TenantAwareJWT: No credentials, staying in public schema")
            return None

        user, token = result
        logger.info(
            "TenantAwareJWT: Authenticated user %s (ID: %s)",
            getattr(user, "email", user.pk),
            user.pk,
        )

        if not getattr(user, "center_id", None):
            request.tenant_schema = "public"
            logger.debug("TenantAwareJWT: User has no center_id, staying in public")
            return (user, token)

        center = self._get_center(user.center_id)
        if center is None:
            request.tenant_schema = "public"
            return (user, token)

        schema_name = center.schema_name
        center_name = center.name
        if not schema_name:
            request.tenant_schema = "public"
            logger.warning(
                "TenantAwareJWT: Center %s has no schema_name", center_name
            )
            return (user, token)

        self._check_center_ready(center, center_name)
        if not getattr(settings, "SKIP_SCHEMA_READY_CHECK", False):
            if not schema_ready(schema_name):
                self._raise_not_ready("SCHEMA_NOT_READY", center_name)

        try:
            set_tenant_schema(schema_name)
            request.tenant_schema = schema_name
            logger.info("TenantAwareJWT: Switched to schema: %s", schema_name)
        except Exception as e:
            logger.exception("TenantAwareJWT: Failed to switch to %s", schema_name)
            set_public_schema()
            request.tenant_schema = "public"
        return (user, token)

    def _get_center(self, center_id):
        from apps.centers.models import Center

        try:
            return Center.objects.only("id", "name", "schema_name", "is_ready").get(
                id=center_id
            )
        except Center.DoesNotExist:
            logger.error(
                "TenantAwareJWT: Center %s does not exist for user", center_id
            )
            return None

    def _check_center_ready(self, center, center_name):
        is_ready = getattr(center, "is_ready", True)
        if not is_ready:
            self._raise_not_ready("CENTER_NOT_READY", center_name)

    def _raise_not_ready(self, error_code, center_name):
        raise AuthenticationFailed(
            {
                "error": error_code,
                "message": (
                    "Your center is still being initialized. "
                    "Please try again in a few moments."
                ),
                "center_name": center_name,
                "retry_after": 10,
            }
        )


