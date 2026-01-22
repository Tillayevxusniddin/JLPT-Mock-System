#apps/core/validators.py
from rest_framework import serializers
from django.core.exceptions import ValidationError

def validate_positive(value):
    if value <= 0:
        raise serializers.ValidationError("This field must be a positive number.")
    return value

def validate_schema_name(value):
    """
    Validate PostgreSQL schema name.
    Must be lowercase alphanumeric with underscores only.
    """
    if not re.match(r'^[a-z0-9_]+$', value):
        raise ValidationError(
            "Schema name must contain only lowercase letters, numbers, and underscores."
        )
    if len(value) > 63:
        raise ValidationError(
            "Schema name must be 63 characters or less (PostgreSQL limit)."
        )
    # Prevent reserved schema names
    reserved = ['public', 'information_schema', 'pg_catalog', 'pg_toast']
    if value in reserved:
        raise ValidationError(
            f"'{value}' is a reserved schema name and cannot be used."
        )
    return value
