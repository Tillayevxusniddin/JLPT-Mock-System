from apps.core.tenant_utils import schema_context
from apps.core.sanitizers import sanitize_text_input
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Group, GroupTeacher, GroupMembership


User = get_user_model()

class GroupListSerializer(serializers.ModelSerializer):
    """Guruhlar ro'yxati uchun yengil serializer"""
    class Meta:
        model = Group
        fields = ('id', 'name', 'level', 'student_count', 'is_active')

class GroupDetailSerializer(serializers.ModelSerializer):
    """Guruh haqida to'liq ma'lumot"""
    teachers = serializers.SerializerMethodField()
    
    class Meta:
        model = Group
        fields = ('id', 'name', 'description', 'level', 'teachers', 'student_count', 'max_students', 'is_active', 'created_at')

    def get_teachers(self, obj):
        """
        Get list of teachers assigned to this group.
        Queries User model from public schema and safely handles missing request context.
        """
        teacher_ids = obj.teacher_assignments.values_list('teacher_id', flat=True)
        
        with schema_context('public'):
            users = User.objects.filter(id__in=teacher_ids)
            
            # Safely get request from context (may be None in tests or async contexts)
            request = self.context.get('request')
            
            return [
                {
                    'id': str(user.id),
                    'full_name': user.get_full_name(),
                    'email': user.email,
                    'avatar': request.build_absolute_uri(user.avatar.url) if (user.avatar and request) else None
                }
                for user in users
            ]

class GroupCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating groups.
    
    ✅ Includes input sanitization for name and description
    ✅ Enforces length limits
    ✅ Strips HTML tags and extra whitespace
    """
    
    class Meta:
        model = Group
        fields = ('id', 'name', 'description', 'level', 'max_students')
    
    def validate_name(self, value):
        """
        Validate and sanitize group name.
        
        Rules:
        - Strip HTML tags and extra whitespace
        - Minimum 2 characters, maximum 100 characters
        - Required field
        """
        if not value:
            raise serializers.ValidationError("Group name is required.")
        
        # Sanitize input
        sanitized = sanitize_text_input(value)
        
        if not sanitized:
            raise serializers.ValidationError("Group name cannot be empty or only whitespace.")
        
        if len(sanitized) < 2:
            raise serializers.ValidationError("Group name must be at least 2 characters long.")
        
        if len(sanitized) > 100:
            raise serializers.ValidationError("Group name cannot exceed 100 characters.")
        
        return sanitized
    
    def validate_description(self, value):
        """
        Validate and sanitize group description.
        
        Rules:
        - Strip HTML tags and extra whitespace
        - Optional field
        - Maximum 500 characters
        """
        if not value:
            return value
        
        # Sanitize input
        sanitized = sanitize_text_input(value)
        
        if sanitized and len(sanitized) > 500:
            raise serializers.ValidationError("Description cannot exceed 500 characters.")
        
        return sanitized
    
    def validate_max_students(self, value):
        """
        Validate maximum student capacity.
        
        Rules:
        - Must be positive integer
        - Minimum 1 student, maximum 100 students
        """
        if value < 1:
            raise serializers.ValidationError("Maximum students must be at least 1.")
        
        if value > 100:
            raise serializers.ValidationError("Maximum students cannot exceed 100.")
        
        return value

class AddMemberSerializer(serializers.Serializer):
    """O'quvchi yoki O'qituvchini guruhga qo'shish uchun"""
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=['TEACHER', 'STUDENT'])
    is_primary = serializers.BooleanField(default=False, required=False) # Faqat teacher uchun

    def validate_user_id(self, value):
        """
        Validate user exists and belongs to same organization.
        CRITICAL: Query User in public schema since we're currently in tenant schema.
        """
        try:
            # ✅ Query User in public schema (User model is in public schema)
            with schema_context('public'):
                user = User.objects.get(id=value)
            
            # Validate request context exists
            request = self.context.get('request')
            if not request:
                raise serializers.ValidationError("Request context required for validation.")
            
            # Validate organization membership
            if user.organization_id != request.user.organization_id:
                raise serializers.ValidationError("User does not belong to your organization.")
            
            # Validate role matches the requested role
            role = self.initial_data.get('role')
            if role == 'TEACHER' and user.role != 'TEACHER':
                raise serializers.ValidationError("User is not a teacher. Cannot assign as teacher.")
            if role == 'STUDENT' and user.role != 'STUDENT':
                raise serializers.ValidationError("User is not a student. Cannot assign as student.")
            
            return value
            
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")