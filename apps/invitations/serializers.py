from rest_framework import serializers
from .models import Invitation

class InvitationCreateSerializer(serializers.ModelSerializer):
    """CenterAdmin yangi kod yaratishi uchun"""
    class Meta:
        model = Invitation
        fields = ('id', 'code', 'role', 'usage_limit', 'expires_at', 'created_at')
        read_only_fields = ('id', 'code', 'created_at')

    def create(self, validated_data):
        # Requestdan user va organizationni olamiz
        request = self.context.get('request')
        validated_data['created_by'] = request.user
        validated_data['organization'] = request.user.organization
        return super().create(validated_data)


class CheckInvitationSerializer(serializers.Serializer):
    """User registratsiyadan oldin kodni tekshirishi uchun"""
    code = serializers.CharField(max_length=12)

    def validate_code(self, value):
        try:
            invite = Invitation.objects.get(code=value)
        except Invitation.DoesNotExist:
            raise serializers.ValidationError("Invitation code not found.")
        
        if not invite.is_valid:
            raise serializers.ValidationError("Invitation code is expired or invalid.")
        
        return value