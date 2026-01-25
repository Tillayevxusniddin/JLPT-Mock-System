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
    mock_test_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        allow_empty=True,
        help_text="List of MockTest UUIDs to assign to this homework"
    )
    quiz_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        allow_empty=True,
        help_text="List of Quiz UUIDs to assign to this homework"
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
    mock_tests = serializers.SerializerMethodField()
    quizzes = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    
    class Meta:
        model = HomeworkAssignment
        fields = [
            "id", "title", "description", "deadline",
            "mock_test_ids", "quiz_ids", "assigned_group_ids", "assigned_user_ids",
            "assigned_groups", "mock_tests", "quizzes",
            "show_results_immediately", "created_by_id", "created_by",
            "created_at", "updated_at"
        ]
        read_only_fields = [
            "id", "created_at", "updated_at", "created_by", "assigned_groups",
            "mock_tests", "quizzes"
        ]

    def get_mock_tests(self, obj):
        """Get list of assigned MockTests."""
        from apps.mock_tests.serializers import MockTestSerializer
        return [
            {"id": str(mt.id), "title": mt.title, "level": mt.level}
            for mt in obj.mock_tests.all()
        ]
    
    def get_quizzes(self, obj):
        """Get list of assigned Quizzes."""
        return [
            {"id": str(q.id), "title": q.title, "description": q.description}
            for q in obj.quizzes.all()
        ]

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
        """Validate the entire object."""
        from django.utils import timezone
        from apps.mock_tests.models import MockTest, Quiz
        
        attrs = super().validate(attrs)
        
        mock_test_ids = attrs.get('mock_test_ids', [])
        quiz_ids = attrs.get('quiz_ids', [])
        group_ids = attrs.get('assigned_group_ids', [])
        user_ids = attrs.get('assigned_user_ids', [])
        deadline = attrs.get('deadline')
        
        # Validate deadline is in the future
        if deadline and deadline <= timezone.now():
            raise serializers.ValidationError({
                "deadline": "Deadline must be in the future."
            })
        
        # Validate at least one resource (MockTest or Quiz) is assigned
        if not mock_test_ids and not quiz_ids:
            raise serializers.ValidationError({
                "detail": "At least one MockTest or Quiz must be assigned."
            })
        
        # Validate MockTests exist and are PUBLISHED
        if mock_test_ids:
            mock_tests = MockTest.objects.filter(id__in=mock_test_ids)
            found_ids = set(mock_tests.values_list('id', flat=True))
            missing_ids = set(mock_test_ids) - found_ids
            if missing_ids:
                raise serializers.ValidationError({
                    "mock_test_ids": f"MockTests not found: {list(missing_ids)}"
                })
            
            for mt in mock_tests:
                if mt.status != MockTest.Status.PUBLISHED:
                    raise serializers.ValidationError({
                        "mock_test_ids": f"MockTest '{mt.title}' is not PUBLISHED."
                    })
                if mt.deleted_at:
                    raise serializers.ValidationError({
                        "mock_test_ids": f"MockTest '{mt.title}' is deleted."
                    })
        
        # Validate Quizzes exist and are active
        if quiz_ids:
            quizzes = Quiz.objects.filter(id__in=quiz_ids)
            found_ids = set(quizzes.values_list('id', flat=True))
            missing_ids = set(quiz_ids) - found_ids
            if missing_ids:
                raise serializers.ValidationError({
                    "quiz_ids": f"Quizzes not found: {list(missing_ids)}"
                })
            
            for q in quizzes:
                if not q.is_active:
                    raise serializers.ValidationError({
                        "quiz_ids": f"Quiz '{q.title}' is not active."
                    })
                if q.deleted_at:
                    raise serializers.ValidationError({
                        "quiz_ids": f"Quiz '{q.title}' is deleted."
                    })
        
        # Validate at least one Group OR one User is assigned
        if not group_ids and not user_ids:
            raise serializers.ValidationError({
                "detail": "At least one group or one user must be assigned."
            })
        
        # Get tenant center_id from request context
        request = self.context.get('request')
        tenant_center_id = None
        if request and hasattr(request, 'user') and request.user:
            tenant_center_id = request.user.center_id
        
        # Validate users belong to tenant
        if user_ids and tenant_center_id:
            try:
                validate_user_ids_belong_to_tenant(user_ids, tenant_center_id)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"assigned_user_ids": str(e)})
        
        # Store validated IDs
        attrs['_validated_mock_test_ids'] = mock_test_ids
        attrs['_validated_quiz_ids'] = quiz_ids
        attrs['_validated_group_ids'] = group_ids
        attrs['_validated_user_ids'] = user_ids
        
        return attrs

    def create(self, validated_data):
        """Create HomeworkAssignment with assigned resources, groups and users."""
        mock_test_ids = validated_data.pop('_validated_mock_test_ids', [])
        quiz_ids = validated_data.pop('_validated_quiz_ids', [])
        group_ids = validated_data.pop('_validated_group_ids', [])
        user_ids = validated_data.pop('_validated_user_ids', [])
        
        assignment = super().create(validated_data)
        
        if mock_test_ids:
            assignment.mock_tests.set(mock_test_ids)
        if quiz_ids:
            assignment.quizzes.set(quiz_ids)
        if group_ids:
            assignment.assigned_groups.set(group_ids)
        if user_ids:
            assignment.assigned_user_ids = user_ids
            assignment.save(update_fields=['assigned_user_ids'])
        
        return assignment

    def update(self, instance, validated_data):
        """Update HomeworkAssignment with assigned resources, groups and users."""
        mock_test_ids = validated_data.pop('_validated_mock_test_ids', None)
        quiz_ids = validated_data.pop('_validated_quiz_ids', None)
        group_ids = validated_data.pop('_validated_group_ids', None)
        user_ids = validated_data.pop('_validated_user_ids', None)
        
        assignment = super().update(instance, validated_data)
        
        if mock_test_ids is not None:
            assignment.mock_tests.set(mock_test_ids)
        if quiz_ids is not None:
            assignment.quizzes.set(quiz_ids)
        if group_ids is not None:
            assignment.assigned_groups.set(group_ids)
        if user_ids is not None:
            assignment.assigned_user_ids = user_ids
            assignment.save(update_fields=['assigned_user_ids'])
        
        return assignment


class HomeworkDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for HomeworkAssignment (student view).
    
    Shows all MockTests and Quizzes with their individual completion status.
    """
    mock_tests = serializers.SerializerMethodField()
    quizzes = serializers.SerializerMethodField()
    assigned_groups = GroupSummarySerializer(many=True, read_only=True)
    
    class Meta:
        model = HomeworkAssignment
        fields = [
            "id", "title", "description", "deadline",
            "mock_tests", "quizzes", "assigned_groups",
            "show_results_immediately", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
    
    def get_mock_tests(self, obj):
        """Get MockTests with completion status."""
        from apps.attempts.models import Submission
        
        user = self.context.get('request').user if self.context.get('request') else None
        if not user:
            return []
        
        mock_tests_data = []
        for mt in obj.mock_tests.all():
            # Check submission status
            submission = Submission.objects.filter(
                user_id=user.id,
                homework_assignment=obj,
                mock_test=mt
            ).first()
            
            status = "Not Started"
            if submission:
                if submission.status == Submission.Status.GRADED:
                    status = "Completed"
                elif submission.status in [Submission.Status.STARTED, Submission.Status.SUBMITTED]:
                    status = "In Progress"
            
            mock_tests_data.append({
                "id": str(mt.id),
                "title": mt.title,
                "level": mt.level,
                "description": mt.description,
                "status": status,
                "type": "mock_test"
            })
        
        return mock_tests_data
    
    def get_quizzes(self, obj):
        """Get Quizzes with completion status."""
        from apps.attempts.models import Submission
        
        user = self.context.get('request').user if self.context.get('request') else None
        if not user:
            return []
        
        quizzes_data = []
        for q in obj.quizzes.all():
            # Check submission status
            submission = Submission.objects.filter(
                user_id=user.id,
                homework_assignment=obj,
                quiz=q
            ).first()
            
            status = "Not Started"
            if submission:
                if submission.status == Submission.Status.GRADED:
                    status = "Completed"
                elif submission.status in [Submission.Status.STARTED, Submission.Status.SUBMITTED]:
                    status = "In Progress"
            
            quizzes_data.append({
                "id": str(q.id),
                "title": q.title,
                "description": q.description,
                "status": status,
                "type": "quiz"
            })
        
        return quizzes_data
