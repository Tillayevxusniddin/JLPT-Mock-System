from rest_framework import serializers
from .models import Invitation


class InvitationSerializer(serializers.ModelSerializer):
    """Full invitation serializer for list/detail views"""
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    is_valid = serializers.BooleanField(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    
    class Meta:
        model = Invitation
        fields = (
            'id', 'code', 'role', 'role_display',
            'organization', 'organization_name',
            'created_by', 'created_by_name',
            'is_active', 'expires_at', 'usage_limit', 'usage_count',
            'is_valid', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'code', 'usage_count', 'created_at', 'updated_at')
    
    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return "Unknown"


class InvitationCreateSerializer(serializers.ModelSerializer):
    """CenterAdmin yangi kod yaratishi uchun"""
    class Meta:
        model = Invitation
        fields = ('id', 'code', 'role', 'usage_limit', 'expires_at', 'created_at')
        read_only_fields = ('id', 'code', 'created_at')

    def validate_role(self, value):
        """CenterAdmin faqat 'TEACHER' va 'STUDENT' rollarini yaratishi mumkin"""
        user = self.context['request'].user
        if user.role == 'CENTERADMIN':
            if value not in ['TEACHER', 'STUDENT']:
                raise serializers.ValidationError("CenterAdmin can only create TEACHER or STUDENT invitations.")
        return value

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