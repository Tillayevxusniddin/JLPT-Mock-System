# apps/authentication/serializers.py
"""
Authentication serializers for multi-tenant JLPT system.

- All User lookups use the default manager (SoftDeleteUserManager), so
  soft-deleted users cannot log in or reset password.
- Email uniqueness is enforced per center (UniqueConstraint + validation).
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from drf_spectacular.utils import extend_schema_field
from django.template.loader import render_to_string
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import User

logger = logging.getLogger(__name__)

try:
    from apps.centers.models import Invitation
except Exception:  # pragma: no cover
    Invitation = None


def get_user_groups_from_tenant(user):
    """Fetch a single user's groups from their center's tenant schema. Use for detail views."""
    if not getattr(user, "center_id", None):
        return []
    try:
        from apps.centers.models import Center
        from apps.core.tenant_utils import with_public_schema, schema_context

        def get_schema_name():
            c = Center.objects.filter(id=user.center_id).values_list("schema_name", flat=True).first()
            return c

        schema_name = with_public_schema(get_schema_name)
        if not schema_name:
            return []

        with schema_context(schema_name):
            from django.db import connection
            from apps.groups.models import GroupMembership

            table_name = GroupMembership._meta.db_table
            if table_name not in connection.introspection.table_names():
                return []

            memberships = GroupMembership.objects.filter(user_id=user.id).values(
                "group__id", "group__name", "role_in_group"
            )
            return [
                {"id": m["group__id"], "name": m["group__name"], "role": m["role_in_group"]}
                for m in memberships
            ]
    except Exception as e:
        logger.exception("Error fetching groups for user %s: %s", user.id, e)
        return []


def get_my_groups_batch(users):
    """
    Batch-fetch my_groups for multiple users. Returns {user_id: [{"id", "name", "role"}, ...]}.
    Call from public schema; uses one schema switch per distinct center_id.
    """
    from apps.centers.models import Center
    from apps.core.tenant_utils import with_public_schema, schema_context
    from apps.groups.models import GroupMembership

    users = [u for u in users if getattr(u, "center_id", None)]
    if not users:
        return {}
    center_ids = {getattr(u, "center_id") for u in users}
    center_schemas = with_public_schema(
        lambda: dict(
            Center.objects.filter(id__in=center_ids).values_list("id", "schema_name")
        )
    )
    result = {u.id: [] for u in users}
    for center_id, schema_name in (center_schemas or {}).items():
        if not schema_name:
            continue
        user_ids_in_center = [u.id for u in users if getattr(u, "center_id") == center_id]
        with schema_context(schema_name):
            from django.db import connection

            table_name = GroupMembership._meta.db_table
            if table_name not in connection.introspection.table_names():
                continue

            memberships = GroupMembership.objects.filter(
                user_id__in=user_ids_in_center
            ).values("user_id", "group__id", "group__name", "role_in_group")
            for m in memberships:
                uid = m["user_id"]
                if uid in result:
                    result[uid].append({
                        "id": m["group__id"],
                        "name": m["group__name"],
                        "role": m["role_in_group"],
                    })
    return result


def get_center_avatars_batch(center_ids):
    """
    Batch-fetch center avatar URLs for given center IDs. Returns {center_id: avatar_url}.
    Call from public schema. Use in list views to avoid N+1 when serializing center_avatar.
    """
    from apps.centers.models import Center
    from apps.core.tenant_utils import with_public_schema

    center_ids = [c for c in center_ids if c is not None]
    if not center_ids:
        return {}
    def _fetch():
        qs = Center.objects.filter(id__in=center_ids).only("id", "avatar")
        return {c.id: (c.avatar.url if c.avatar else None) for c in qs}

    return with_public_schema(_fetch) or {}


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.ChoiceField(
        choices=[("TEACHER", "Teacher"), ("STUDENT", "Student")]
    )

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "avatar",
            "role", "password", "is_active",
        ]

    def validate_email(self, value):
        request = self.context.get("request")
        if not request or not getattr(request.user, "center_id", None):
            return value
        if User.objects.filter(email=value, center_id=request.user.center_id).exists():
            raise serializers.ValidationError(
                "A user with this email already exists in this center."
            )
        return value

    def create(self, validated_data):
        from django.db import transaction

        request = self.context.get("request")
        validated_data["center_id"] = request.user.center_id
        validated_data["is_approved"] = True
        password = validated_data.pop("password")

        with transaction.atomic():
            user = User.objects.create_user(**validated_data)
            user.set_password(password)
            user.save()
        return user

class UserListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for user list views.
    
    NOTE: my_groups field intentionally excluded to prevent N+1 schema switching.
    Each call to get_user_groups_from_tenant() switches database schema per user,
    causing severe performance degradation in list views.
    
    For group information, use UserSerializer (detail view) instead.
    """
    center_avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "avatar", 
            "role", "center", "center_avatar", 
            "is_approved", "created_at"
        ]
        read_only_fields = ["id", "role", "center", "is_approved"]

    @extend_schema_field(serializers.CharField(allow_null=True, help_text="Center avatar URL"))
    def get_center_avatar(self, obj):
        if not obj.center_id:
            return None
        center_avatar_map = self.context.get("center_avatar_map") or {}
        if obj.center_id in center_avatar_map:
            return center_avatar_map[obj.center_id]
        try:
            from apps.core.tenant_utils import with_public_schema
            from apps.centers.models import Center

            def _get():
                c = Center.objects.filter(id=obj.center_id).first()
                return c.avatar.url if c and c.avatar else None

            return with_public_schema(_get)
        except Exception:
            return None

    
class UserSerializer(serializers.ModelSerializer):
    my_groups = serializers.SerializerMethodField()
    center_info = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "avatar",
            "bio", "address", "city", "emergency_contact_phone",
            "role", "center", "center_info",
            "my_groups", "is_approved", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "role", "center", "is_approved"]
    
    @extend_schema_field(serializers.ListField(child=serializers.DictField(), help_text="List of groups"))
    def get_my_groups(self, obj):
        my_groups_map = self.context.get("my_groups_map") or {}
        if obj.id in my_groups_map:
            return my_groups_map[obj.id]
        return get_user_groups_from_tenant(obj)

    @extend_schema_field(serializers.DictField(allow_null=True, help_text="Center info object"))
    def get_center_info(self, obj):
        if not obj.center_id:
            return None
        try:
            from apps.core.tenant_utils import with_public_schema
            from apps.centers.models import Center

            def _get():
                center = Center.objects.filter(id=obj.center_id).first()
                if not center:
                    return None
                return {
                    "id": center.id,
                    "name": center.name,
                    "is_active": center.is_active,
                }

            return with_public_schema(_get)
        except Exception:
            return None

class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "avatar", "email"]
        read_only_fields = ["id"]

class UserManagementSerializer(serializers.ModelSerializer):
    my_groups = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "avatar", 
            "role", "is_active", "is_approved",
            "my_groups", "created_at"
        ]
        read_only_fields = ["id", "role", "created_at", "email"]

    @extend_schema_field(serializers.ListField(child=serializers.DictField(), help_text="List of groups"))
    def get_my_groups(self, obj):
        my_groups_map = self.context.get("my_groups_map") or {}
        if obj.id in my_groups_map:
            return my_groups_map[obj.id]
        return get_user_groups_from_tenant(obj)

    def validate_email(self, value):
        request = self.context.get("request")
        if not request or not getattr(request.user, "center_id", None):
            return value
        if User.objects.filter(email=value, center_id=request.user.center_id).exists():
            raise serializers.ValidationError(
                "A user with this email already exists in this center."
            )
        return value

    def create(self, validated_data):
        from django.db import transaction

        from apps.centers.models import Center
        from apps.core.tenant_utils import set_public_schema

        password = validated_data.pop("password", None)
        request = self.context.get("request")
        set_public_schema()
        validated_data["center"] = Center.objects.get(id=request.user.center_id)

        with transaction.atomic():
            user = User.objects.create_user(**validated_data)
            if password:
                user.set_password(password)
                user.save()
        return user

class RegisterSerializer(serializers.ModelSerializer):
    invitation_code = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, required=True, min_length=6)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "password", "invitation_code"]
        read_only_fields = ["id"]

    def validate(self, data):
        if Invitation is None:
            raise serializers.ValidationError(
                {"invitation_code": "Invitation feature unavailable."}
            )
        code = data.get("invitation_code")
        if not code:
            raise serializers.ValidationError(
                {"invitation_code": "Invitation code is required."}
            )
        try:
            invitation = Invitation.objects.get(code=code, status="PENDING")
        except Invitation.DoesNotExist:
            raise serializers.ValidationError({"invitation_code": "Invalid code."})
        if invitation.target_user_id is not None:
            raise serializers.ValidationError(
                {"invitation_code": "Invitation already claimed."}
            )
        if invitation.is_expired:
            raise serializers.ValidationError(
                {"invitation_code": "Invitation expired."}
            )
        if invitation.role in (User.Role.OWNER, User.Role.CENTERADMIN):
            raise serializers.ValidationError({
                "invitation_code": (
                    "Administrators cannot register via public API. "
                    "Please contact system support."
                ),
            })
        email = data.get("email")
        if email and User.objects.filter(email=email, center_id=invitation.center_id).exists():
            raise serializers.ValidationError(
                {"email": "A user with this email already exists in this center."}
            )
        data["_invitation"] = invitation
        data.pop("invitation_code", None)
        return data

    def create(self, validated_data):
        from django.db import transaction

        invitation = validated_data.pop("_invitation")
        password = validated_data.pop("password")
        with transaction.atomic():
            invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
            if invitation.target_user_id is not None:
                raise serializers.ValidationError(
                    {"invitation_code": "Invitation already claimed."}
                )
            user = User.objects.create_user(
                role=invitation.role,
                center=invitation.center,
                is_approved=False,
                password=password,
                **validated_data,
            )
            invitation.target_user = user
            invitation.save(update_fields=["target_user_id"])
        return user

class LogoutRequestSerializer(serializers.Serializer):
    """Request body for Logout: only the refresh token is required (same token returned by Login)."""

    refresh = serializers.CharField(
        required=True,
        help_text="JWT refresh token to blacklist; required for logout.",
    )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    user = UserSerializer(read_only=True)

    def validate(self, data):
        user = authenticate(
            request=self.context.get("request"),
            username=data["email"],
            password=data["password"],
        )
        if not user:
            raise serializers.ValidationError({"detail": "Invalid credentials."})
        if not user.is_active:
            raise serializers.ValidationError({"detail": "User account is disabled."})
        if not user.is_approved:
            raise serializers.ValidationError({"detail": "Account pending approval."})
        if user.center and user.role != User.Role.OWNER:
            if not user.center.is_active: 
                raise serializers.ValidationError({
                    "detail": "This center is currently suspended. Please contact support."
                })

        tokens = RefreshToken.for_user(user)
        return {"access": str(tokens.access_token), "refresh": str(tokens), "user": user}

class UpdatePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate(self, data):
        user: User = self.context["request"].user
        if not user.check_password(data["old_password"]):
            raise serializers.ValidationError({"old_password": "Incorrect old password."})
        validate_password(data["new_password"], user)
        return data

    def save(self, **kwargs):
        user: User = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, data):
        # Use filter().first() so soft-deleted users (excluded by default manager) are ignored.
        # Do not leak user existence: always return same success message.
        data["user"] = User.objects.filter(
            email=data["email"],
            is_active=True,
        ).first()
        return data

    def save(self, **kwargs):
        user = self.validated_data.get("user")
        if not user:
            # Don't reveal whether user exists; just return success
            return {"detail": "Password reset email sent."}
        
        # Generate token and uid
        token = PasswordResetTokenGenerator().make_token(user)
        uidb64 = urlsafe_base64_encode(str(user.id).encode())
        
        # Construct frontend reset URL with query parameters
        frontend_base = getattr(settings, "FRONTEND_URL_BASE", "http://localhost:3000")
        reset_url = f"{frontend_base}/auth/forgot-password/password/?uid={uidb64}&token={token}"
        
        # Render email template (fallback to plain text if missing)
        try:
            html_message = render_to_string("email/password_reset_email.html", {
                "user": user,
                "reset_url": reset_url,
            })
        except Exception:
            html_message = None
        
        # Send email
        try:
            send_mail(
                subject="Password Reset - 404 EDU",
                message=f"To reset your password, visit the following link: {reset_url}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            logger.exception(
                "Failed to send password reset email to %s: %s",
                user.email,
                e,
                extra={"user_id": user.id},
            )
            # Return same message so we don't leak send failure to client
        return {"detail": "Password reset email sent."}

class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate(self, data):
        try:
            raw = urlsafe_base64_decode(data["uid"])
            uid = int(force_str(raw))
        except (TypeError, ValueError):
            raise serializers.ValidationError(
                {"uid": "Invalid or expired link."}
            )
        user = User.objects.filter(id=uid, is_active=True).first()
        if not user:
            raise serializers.ValidationError(
                {"uid": "Invalid or expired link."}
            )
        if not PasswordResetTokenGenerator().check_token(user, data["token"]):
            raise serializers.ValidationError(
                {"token": "Invalid or expired link."}
            )
        validate_password(data["new_password"], user)
        data["user"] = user
        return data

    def save(self, **kwargs):
        user: User = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


    
    












