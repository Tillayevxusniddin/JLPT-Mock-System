#apps/authentication/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from apps.authentication.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from drf_spectacular.utils import extend_schema_field
import logging

logger = logging.getLogger(__name__)
try:
    from apps.centers.models import Invitation
except Exception:  # pragma: no cover
    Invitation = None


def get_user_groups_from_tenant(user):
    if not user.center_id:
        return []
    try:
        from apps.centers.models import Center
        from apps.core.tenant_utils import with_public_schema, schema_context

        def get_schema_name():
            try:
                return Center.objects.values_list('schema_name', flat=True).get(id=user.center_id)
            except Center.DoesNotExist:
                return None
    
        schema_name = with_public_schema(get_schema_name)
        if not schema_name:
            return []

        with schema_context(schema_name):
            from apps.groups.models import GroupMembership

            memberships = GroupMembership.objects.filter(
                user_id=user.id
            ).select_related('group').values(
                'group__id', 'group__name', 'role_in_group'
            )

            return [
                {
                    "id": m['group__id'],
                    "name": m['group__name'],
                    "role": m['role_in_group']
                }
                for m in memberships
            ]
    except Exception as e:
        logger.error(f"Error fetching groups for user {user.id}: {e}")
        return []


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.ChoiceField(choices=[('TEACHER', 'Teacher'), ('STUDENT', 'Student')])

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "avatar", 
            "role", "password", "is_active"
        ]

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

    def get_center_avatar(self, obj):
        if not obj.center_id: return None
        try:
            from apps.core.tenant_utils import with_public_schema
            from apps.centers.models import Center
            return with_public_schema(lambda: Center.objects.get(id=obj.center_id).avatar.url if Center.objects.get(id=obj.center_id).avatar else None)
        except: return None

    
class UserSerializer(serializers.ModelSerializer):
    my_groups = serializers.SerializerMethodField()
    center_info = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "avatar", 
            "role", "center", "center_info",
            "my_groups", "is_approved", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "role", "center", "is_approved"]
    
    def get_my_groups(self, obj):
        return get_user_groups_from_tenant(obj)

    def get_center_info(self, obj):
        if not obj.center_id: return None
        try:
            from apps.core.tenant_utils import with_public_schema
            from apps.centers.models import Center
            return with_public_schema(lambda: list(Center.objects.filter(id=obj.center_id).values('id', 'name', 'is_active'))[0])
        except: return None

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

    def get_my_groups(self, obj):
        return get_user_groups_from_tenant(obj)

    def create(self, validated_data):
        from django.db import transaction
        password = validated_data.pop("password", None)
        request = self.context.get("request")
        from apps.core.tenant_utils import set_public_schema
        from apps.centers.models import Center
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
        from django.db import transaction
        if Invitation is None:
            raise serializers.ValidationError({"invitation_code": "Invitation feature unavailable."})

        code = data.get("invitation_code")
        if not code:
            raise serializers.ValidationError({"invitation_code": "Invitation code is required."})
        try:
            with transaction.atomic():
                invitation = Invitation.objects.select_for_update().get(code=code, status="PENDING")
                if invitation.target_user_id is not None:
                    raise serializers.ValidationError({"invitation_code": "Invitation already claimed."})
                if invitation.is_expired:
                    raise serializers.ValidationError({"invitation_code": "Invitation expired."})
                if invitation.role in ['OWNER', 'CENTER_ADMIN']:
                    raise serializers.ValidationError({
                        "invitation_code": "Administrators cannot register via public API. Please contact system support."
                    })
        except Invitation.DoesNotExist:
            raise serializers.ValidationError({"invitation_code": "Invalid code."})
        data["_invitation"] = invitation
        data.pop("invitation_code", None)
        return data

    def create(self, validated_data):

        from django.db import transaction
        invitation = validated_data.pop("_invitation")
        password = validated_data.pop("password")
        with transaction.atomic():
            user = User.objects.create_user(
                role=invitation.role,
                center=invitation.center,
                is_approved=False,
                password=password,
                **validated_data
            )
        invitation.target_user = user
        invitation.save()
        return user

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
        if user.center and user.role != "OWNER":
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
        try:
            data["user"] = User.objects.get(email=data["email"], is_active=True)
        except User.DoesNotExist:
            # Do not leak existence; still pretend success
            data["user"] = None
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
        
        # Render email template
        html_message = render_to_string("email/password_reset_email.html", {
            "user": user,
            "reset_url": reset_url,
        })
        
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
            # Log the error but don't reveal it to the user
            logger.error(
                f"Failed to send password reset email to {user.email}: {e}",
                exc_info=True,
                extra={"user_id": user.id, "email": user.email}
            )
        
        return {"detail": "Password reset email sent."}

class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate(self, data):
        # Decode uid (BigAutoField id)
        try:
            uid = int(force_str(urlsafe_base64_decode(data["uid"])))
            user = User.objects.get(id=uid, is_active=True)
        except Exception:
            raise serializers.ValidationError({"uid": "Invalid or expired token."})
        if not PasswordResetTokenGenerator().check_token(user, data["token"]):
            raise serializers.ValidationError({"token": "Invalid or expired token."})
        validate_password(data["new_password"], user)
        data["user"] = user
        return data

    def save(self, **kwargs):
        user: User = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


    
    












