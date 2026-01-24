# apps/assignments/serializers.py

from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import ExamAssignment, HomeworkAssignment
from .services import validate_assignment_payload, validate_user_ids_belong_to_tenant
from apps.groups.models import Group


class UserSummarySerializer(serializers.Serializer):
    """Serializer for user summary information (cross-schema)."""
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    email = serializers.EmailField(required=False)

    @staticmethod
    def from_user(user):
        """Create a user summary from a User instance."""
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
            "email": getattr(user, "email", None) or ""
        }


class GroupSummarySerializer(serializers.ModelSerializer):
    """Serializer for Group summary."""
    
    class Meta:
        model = Group
        fields = ['id', 'name']


class ExamAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for ExamAssignment model."""
    mock_test = serializers.PrimaryKeyRelatedField(
        queryset=None,  # Will be set in __init__
        required=True,
        help_text="MockTest instance (must be PUBLISHED)"
    )
    assigned_group_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        allow_empty=True,
        help_text="List of Group UUIDs to assign this exam to"
    )
    assigned_groups = GroupSummarySerializer(many=True, read_only=True)
    created_by = serializers.SerializerMethodField()
    
    class Meta:
        model = ExamAssignment
        fields = [
            "id", "title", "description", "mock_test", "status",
            "estimated_start_time", "is_published", "assigned_group_ids",
            "assigned_groups", "created_by_id", "created_by",
            "created_at", "updated_at"
        ]
        read_only_fields = [
            "id", "created_at", "updated_at", "created_by", "assigned_groups"
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set queryset for mock_test field
        from apps.mock_tests.models import MockTest
        self.fields['mock_test'].queryset = MockTest.objects.filter(
            status=MockTest.Status.PUBLISHED,
            deleted_at__isnull=True
        )

    def get_created_by(self, obj):
        """Get user information from public schema."""
        if not obj.created_by_id:
            return None
        
        user_map = self.context.get('user_map')
        if user_map is not None:
            user = user_map.get(obj.created_by_id)
            if user:
                return UserSummarySerializer.from_user(user)
        
        # Fallback: fetch from public schema
        from apps.core.tenant_utils import with_public_schema
        from apps.authentication.models import User
        
        def fetch_user():
            return User.objects.filter(id=obj.created_by_id).first()
        
        user = with_public_schema(fetch_user)
        return UserSummarySerializer.from_user(user)

    def validate(self, attrs):
        """Validate the entire object using service function."""
        attrs = super().validate(attrs)
        
        mock_test = attrs.get('mock_test') or (self.instance.mock_test if self.instance else None)
        group_ids = attrs.get('assigned_group_ids', [])
        
        if not mock_test:
            raise serializers.ValidationError({
                "mock_test": "MockTest is required."
            })
        
        try:
            validated_data = validate_assignment_payload(
                mock_test=mock_test,
                group_ids=group_ids if group_ids else None,
                user_ids=None  # ExamAssignment doesn't use user_ids
            )
            # Update attrs with validated data
            attrs['mock_test'] = validated_data['mock_test']
            attrs['_validated_group_ids'] = validated_data['group_ids']
        except DjangoValidationError as e:
            raise serializers.ValidationError({"detail": str(e)})
        
        return attrs

    def create(self, validated_data):
        """Create ExamAssignment with assigned groups."""
        group_ids = validated_data.pop('_validated_group_ids', [])
        assignment = super().create(validated_data)
        
        if group_ids:
            assignment.assigned_groups.set(group_ids)
        
        return assignment

    def update(self, instance, validated_data):
        """Update ExamAssignment with assigned groups."""
        group_ids = validated_data.pop('_validated_group_ids', None)
        assignment = super().update(instance, validated_data)
        
        if group_ids is not None:
            assignment.assigned_groups.set(group_ids)
        
        return assignment


class HomeworkAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for HomeworkAssignment model."""
    mock_test = serializers.PrimaryKeyRelatedField(
        queryset=None,  # Will be set in __init__
        required=True,
        help_text="MockTest instance (must be PUBLISHED)"
    )
    assigned_group_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        allow_empty=True,
        help_text="List of Group UUIDs to assign this homework to"
    )
    assigned_user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text="List of User IDs (integers) to assign individually"
    )
    assigned_groups = GroupSummarySerializer(many=True, read_only=True)
    created_by = serializers.SerializerMethodField()
    
    class Meta:
        model = HomeworkAssignment
        fields = [
            "id", "title", "description", "deadline", "mock_test",
            "assigned_group_ids", "assigned_user_ids", "assigned_groups",
            "show_results_immediately", "created_by_id", "created_by",
            "created_at", "updated_at"
        ]
        read_only_fields = [
            "id", "created_at", "updated_at", "created_by", "assigned_groups"
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set queryset for mock_test field
        from apps.mock_tests.models import MockTest
        self.fields['mock_test'].queryset = MockTest.objects.filter(
            status=MockTest.Status.PUBLISHED,
            deleted_at__isnull=True
        )

    def get_created_by(self, obj):
        """Get user information from public schema."""
        if not obj.created_by_id:
            return None
        
        user_map = self.context.get('user_map')
        if user_map is not None:
            user = user_map.get(obj.created_by_id)
            if user:
                return UserSummarySerializer.from_user(user)
        
        # Fallback: fetch from public schema
        from apps.core.tenant_utils import with_public_schema
        from apps.authentication.models import User
        
        def fetch_user():
            return User.objects.filter(id=obj.created_by_id).first()
        
        user = with_public_schema(fetch_user)
        return UserSummarySerializer.from_user(user)

    def validate(self, attrs):
        """Validate the entire object using service function."""
        attrs = super().validate(attrs)
        
        mock_test = attrs.get('mock_test') or (self.instance.mock_test if self.instance else None)
        group_ids = attrs.get('assigned_group_ids', [])
        user_ids = attrs.get('assigned_user_ids', [])
        
        if not mock_test:
            raise serializers.ValidationError({
                "mock_test": "MockTest is required."
            })
        
        # Get tenant center_id from request context
        request = self.context.get('request')
        tenant_center_id = None
        if request and hasattr(request, 'user') and request.user:
            tenant_center_id = request.user.center_id
        
        try:
            validated_data = validate_assignment_payload(
                mock_test=mock_test,
                group_ids=group_ids if group_ids else None,
                user_ids=user_ids if user_ids else None
            )
            # Update attrs with validated data
            attrs['mock_test'] = validated_data['mock_test']
            attrs['_validated_group_ids'] = validated_data['group_ids']
            attrs['_validated_user_ids'] = validated_data['user_ids']
            
            # Validate users belong to tenant
            if validated_data['user_ids'] and tenant_center_id:
                validate_user_ids_belong_to_tenant(
                    validated_data['user_ids'],
                    tenant_center_id
                )
        except DjangoValidationError as e:
            raise serializers.ValidationError({"detail": str(e)})
        
        return attrs

    def create(self, validated_data):
        """Create HomeworkAssignment with assigned groups and users."""
        group_ids = validated_data.pop('_validated_group_ids', [])
        user_ids = validated_data.pop('_validated_user_ids', [])
        assignment = super().create(validated_data)
        
        if group_ids:
            assignment.assigned_groups.set(group_ids)
        
        if user_ids:
            assignment.assigned_user_ids = user_ids
            assignment.save(update_fields=['assigned_user_ids'])
        
        return assignment

    def update(self, instance, validated_data):
        """Update HomeworkAssignment with assigned groups and users."""
        group_ids = validated_data.pop('_validated_group_ids', None)
        user_ids = validated_data.pop('_validated_user_ids', None)
        assignment = super().update(instance, validated_data)
        
        if group_ids is not None:
            assignment.assigned_groups.set(group_ids)
        
        if user_ids is not None:
            assignment.assigned_user_ids = user_ids
            assignment.save(update_fields=['assigned_user_ids'])
        
        return assignment
