from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from apps.invitations.models import Invitation

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'role', 'organization', 'avatar', 'is_approved')
        read_only_fields = ('id', 'role', 'organization', 'is_approved')

class RegisterSerializer(serializers.ModelSerializer):
    """
    Faqat Invitation Code orqali ro'yxatdan o'tish.
    """
    invite_code = serializers.CharField(write_only=True, required=True)
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = User
        fields = ('email', 'password', 'first_name', 'last_name', 'phone', 'invite_code')

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
            # 1. User yaratamiz
            user = User.objects.create_user(
                email=validated_data['email'],
                password=password,
                first_name=validated_data['first_name'],
                last_name=validated_data['last_name'],
                phone=validated_data.get('phone', ''),
                
                # Invitationdan ma'lumotlarni olamiz
                role=invite.role,
                organization=invite.organization,
                
                # CenterAdmin tasdiqlashi kerak
                is_approved=False, 
                is_active=True 
            )

            # 2. Invitation statistikasini yangilaymiz
            invite.usage_count += 1
            invite.save()

        return user

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Tasdiqlanmagan user kira olmasligi kerak
        if not self.user.is_approved and not self.user.is_owner:
             raise serializers.ValidationError(
                 {"detail": "Sizning akkauntingiz hali administrator tomonidan tasdiqlanmagan."}
             )
             
        user_serializer = UserSerializer(self.user)
        data.update(user_serializer.data)
        return data