# apps/core/serializers.py
"""
Shared serializers and display helpers for multi-tenant JLPT.
- UserSummarySerializer: consistent Public User representation (id, full_name, email).
- user_display_from_map: string display for user_id from batch-fetched user_map (no N+1).
"""

from rest_framework import serializers


class BaseSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        abstract = True


class UserSummarySerializer(serializers.Serializer):
    """Single source of truth for Public User summary (id, full_name, email). Used in tenant list views with user_map."""
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    email = serializers.EmailField(required=False)

    @staticmethod
    def from_user(user):
        """Build summary dict from a User instance (public schema)."""
        if not user:
            return None
        full_name = ""
        if getattr(user, "first_name", None) or getattr(user, "last_name", None):
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not full_name:
            full_name = getattr(user, "email", None) or getattr(user, "username", None) or str(user.id)
        return {
            "id": user.id,
            "full_name": full_name.strip(),
            "email": getattr(user, "email", None) or "",
        }


def user_display_from_map(user_map, user_id):
    """Return display string for user_id from user_map (public schema); avoids N+1 in list serializers."""
    if not user_id or not user_map:
        return ""
    user = user_map.get(user_id)
    if not user:
        return ""
    summary = UserSummarySerializer.from_user(user)
    return (summary or {}).get("full_name") or (summary or {}).get("email") or str(user_id)
    