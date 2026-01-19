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
                    raise serializers.ValidationError({"invitation_code": "This invitation is already pending approval for another user."})
                if invitation.is_expired:
                    raise serializers.ValidationError({"invitation_code": "This invitation has expired."})
                
        except Invitation.DoesNotExist:
            raise serializers.ValidationError({"invitation_code": "Invalid or expired invitation code."})

        password = data.get("password")
        if not password or password == "":
            raise serializers.ValidationError({"password": "Password is required for all accounts."})
        if not data.get("first_name") or not data.get("last_name"):
            raise serializers.ValidationError({"first_name": "First name is required.", "last_name": "Last name is required."})

        data["_invitation"] = invitation
        data.pop("invitation_code", None)
        return data
















