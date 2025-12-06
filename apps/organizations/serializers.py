from rest_framework import serializers
from .models import Organization


class OrganizationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for nested organization data"""
    class Meta:
        model = Organization
        fields = ('id', 'name', 'logo', 'status')
        read_only_fields = ('id', 'name', 'logo', 'status')


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = (
            'id', 'name', 'slug', 'schema_name', 'description', 
            'logo', 'status', 'is_active', 'is_trial',
            'max_students', 'max_teachers', 'created_at'
        )
        # Owner schema nomini va limitlarni o'zgartira olmasligi kerak (ularni Admin panel yoki Superuser qiladi)
        read_only_fields = ('id', 'slug', 'schema_name', 'status', 'max_students', 'max_teachers', 'created_at')
    
    #TODO  Magic Bytes and check with pillow
    def validate_logo(self, value):
        """Validate logo file size (max 5MB) and format"""
        if value:
            # Check file size
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError("Logo file size cannot exceed 5MB")
            
            # Check file format
            allowed_formats = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
            if hasattr(value, 'content_type') and value.content_type not in allowed_formats:
                raise serializers.ValidationError(
                    "Logo must be in JPEG, PNG, GIF, or WebP format"
                )
        return value