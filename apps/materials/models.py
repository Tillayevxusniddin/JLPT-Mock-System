#apps/materials/models.py
import logging
from django.db import models
from apps.core.models import TenantBaseModel
from apps.core.tenant_utils import get_current_schema

logger = logging.getLogger(__name__)


def tenant_material_upload_path(instance, filename):
    """
    Tenant-isolated upload path for S3/storage. Never relies on connection.tenant.
    Uses get_current_schema() and Center lookup in public schema; fallback to
    schema_name to prevent file collisions between centers.
    
    SECURITY NOTE: Logs all Center lookup failures for monitoring.
    """
    from apps.core.tenant_utils import with_public_schema
    from apps.centers.models import Center

    schema_name = get_current_schema() or "public"

    if schema_name == "public":
        return f"materials/{filename}"

    try:
        center = with_public_schema(
            lambda: Center.objects.filter(schema_name=schema_name).first()
        )
        if center is not None:
            return f"tenants/{center.id}/materials/{filename}"
    except Exception as e:
        # SECURITY FIX: Log the Center lookup failure for monitoring/debugging
        logger.error(
            f"Center lookup failed for schema_name={schema_name}. "
            f"Falling back to schema-based path. Error: {e}",
            exc_info=True
        )
    
    logger.warning(
        f"Using schema_name-based fallback path for material upload: "
        f"schema={schema_name}, filename={filename}"
    )
    return f"tenants/{schema_name}/materials/{filename}"


class Material(TenantBaseModel):
    class FileType(models.TextChoices):
        AUDIO = "AUDIO", "Audio"
        PDF = "PDF", "PDF"
        DOCX = "DOCX", "DOCX"
        IMAGE = "IMAGE", "Image"
        OTHER = "OTHER", "Other"


    name = models.CharField(max_length=200)
    file = models.FileField(upload_to=tenant_material_upload_path)
    file_type = models.CharField(max_length=10, choices=FileType.choices, default=FileType.OTHER)

    created_by_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="ID of the user (User) who uploaded this material in the public schema"
    )

    is_public = models.BooleanField(
        default=False,
        help_text="If True, visible to ALL students in center. If False, only assigned groups/students can access."
    )
    
    # NEW: Link materials to specific groups
    groups = models.ManyToManyField(
        "groups.Group",
        related_name="materials",
        blank=True,
        help_text="Groups that have access to this material (if not public)."
    )

    def __str__(self) -> str:
        return self.name


    @property
    def created_by(self):
        """Fetch the creator User object from the public schema."""
        if self.created_by_id:
            from apps.authentication.models import User  # FIXED: Correct import path
            from apps.core.tenant_utils import with_public_schema
            try:
                # Wrap in with_public_schema to ensure User lookup works from tenant context
                return with_public_schema(lambda: User.objects.get(id=self.created_by_id))
            except User.DoesNotExist:
                return None
        return None

    def soft_delete(self):
        """
        Soft-delete material.
        NOTE: Physical file deletion happens via post_delete signal or logic 
        checking for hard deletion, not during soft delete.
        """
        return super().soft_delete()