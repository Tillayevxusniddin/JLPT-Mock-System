from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.db import transaction
from django.db.models import F
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from apps.invitations.models import Invitation
from apps.core.sanitizers import sanitize_text_input, sanitize_email, sanitize_phone

User = get_user_model()


class UserListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for user lists"""
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    
    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'role', 'role_display', 'is_approved', 'avatar')
        read_only_fields = ('id', 'role', 'role_display', 'is_approved')

class UserDetailSerializer(serializers.ModelSerializer):
    """Comprehensive serializer for user detail/profile"""
    
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    organization = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = (
            'id', 'email', 'first_name', 'last_name', 'phone',
            'role', 'role_display', 'organization', 
            'avatar', 'avatar_url', 'date_of_birth',
            'is_approved', 'is_active', 'is_email_verified',
            'language', 'timezone', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'role', 'organization', 'is_approved', 'created_at', 'updated_at')
    
    def get_organization(self, obj):
        """Return organization data without circular import"""
        if obj.organization:
            return {
                'id': obj.organization.id,
                'name': obj.organization.name,
                'logo': obj.organization.logo.url if obj.organization.logo else None,
                'status': obj.organization.status,
            }
        return None
    
    def get_avatar_url(self, obj):
        if obj.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None

class UserSerializer(UserDetailSerializer):
    """Alias for backward compatibility - use UserDetailSerializer"""
    pass

class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile (excluding sensitive fields)"""
    
    class Meta:
        model = User
        fields = (
            'first_name', 'last_name', 'phone', 
            'avatar', 'date_of_birth', 
            'language', 'timezone'
        )
    
    def validate_first_name(self, value):
        """Sanitize first name"""
        return sanitize_text_input(value)
    
    def validate_last_name(self, value):
        """Sanitize last name"""
        return sanitize_text_input(value)
    
    def validate_phone(self, value):
        """Sanitize phone number"""
        return sanitize_phone(value) if value else value
    
    def validate_avatar(self, value):
        """Validate avatar file size (max 5MB) and format"""
        if value:
            # Check file size
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError("Avatar file size cannot exceed 5MB")
            
            # Check file format
            allowed_formats = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
            if hasattr(value, 'content_type') and value.content_type not in allowed_formats:
                raise serializers.ValidationError(
                    "Avatar must be in JPEG, PNG, GIF, or WebP format"
                )
        return value

class RegisterSerializer(serializers.ModelSerializer):
    """
    Faqat Invitation Code orqali ro'yxatdan o'tish.
    """
    invite_code = serializers.CharField(write_only=True, required=True)
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = User
        fields = ('email', 'password', 'first_name', 'last_name', 'phone', 'invite_code')
    
    def validate_email(self, value):
        """Sanitize and validate email"""
        return sanitize_email(value)
    
    def validate_first_name(self, value):
        """Sanitize first name"""
        return sanitize_text_input(value)
    
    def validate_last_name(self, value):
        """Sanitize last name"""
        return sanitize_text_input(value)
    
    def validate_phone(self, value):
        """Sanitize phone number"""
        return sanitize_phone(value) if value else value

    def validate_invite_code(self, value):
        try:
            invite = Invitation.objects.get(code=value)
            if not invite.is_valid:
                raise serializers.ValidationError("Ushbu taklif kodi eskirgan yoki limiti tugagan.")
            return invite
        except Invitation.DoesNotExist:
            raise serializers.ValidationError("Bunday taklif kodi mavjud emas.")

    def create(self, validated_data):
        invite = validated_data.pop('invite_code')
        password = validated_data.pop('password')

        with transaction.atomic():
            # Lock the invitation row to prevent race conditions
            invite = Invitation.objects.select_for_update().get(pk=invite.pk)
            
            # Double-check validity after locking (in case usage_limit was reached)
            if not invite.is_valid:
                raise serializers.ValidationError({
                    "invite_code": "This invitation code is no longer valid."
                })
            
            # 1. Create user
            user = User.objects.create_user(
                email=validated_data['email'],
                password=password,
                first_name=validated_data['first_name'],
                last_name=validated_data['last_name'],
                phone=validated_data.get('phone', ''),
                
                # Get info from invitation
                role=invite.role,
                organization=invite.organization,
                
                # Requires CenterAdmin approval
                is_approved=False, 
                is_active=True 
            )
            
            # 2. Create user profile
            from apps.authentication.models import UserProfile
            UserProfile.objects.create(user=user)

            # 3. Update invitation statistics using F() to prevent race conditions
            Invitation.objects.filter(pk=invite.pk).update(
                usage_count=F('usage_count') + 1
            )

        return user

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Tasdiqlanmagan user kira olmasligi kerak
        if not self.user.is_approved and not self.user.is_owner:
             raise serializers.ValidationError(
                 {"detail": "Sizning akkauntingiz hali administrator tomonidan tasdiqlanmagan."}
             )
             
        # Include full user details in login response
        user_serializer = UserDetailSerializer(self.user, context={'request': self.context.get('request')})
        data['user'] = user_serializer.data
        return data

class PasswordChangeSerializer(serializers.Serializer):
    """Serializer for password change endpoint"""
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, min_length=8)
    confirm_password = serializers.CharField(required=True, write_only=True)
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs
    
    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user

class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for requesting password reset"""
    email = serializers.EmailField(required=True)
    
    def validate_email(self, value):
        try:
            user = User.objects.get(email=value.lower())
            self.context['user'] = user
        except User.DoesNotExist:
            # Don't reveal that user doesn't exist for security
            pass
        return value
    
    def save(self):
        user = self.context.get('user')
        if user:
            # Generate token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # TODO: Send email with reset link
            # For now, return token (in production, only send via email)
            return {
                'uid': uid,
                'token': token,
                'email': user.email
            }
        return None

class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for confirming password reset"""
    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, write_only=True, min_length=8)
    confirm_password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        
        # Decode user ID
        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError("Invalid reset link.")
        
        # Verify token
        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError("Invalid or expired reset link.")
        
        self.context['user'] = user
        return attrs
    
    def save(self):
        user = self.context['user']
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user