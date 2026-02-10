# apps/assignments/serializers.py
"""
Assignments serializers. Visibility, validation rules, and student status
(Not Started / In Progress / Completed) are documented in apps/assignments/swagger.py.
"""

from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from .models import ExamAssignment, HomeworkAssignment
from .services import validate_assignment_payload, validate_user_ids_belong_to_tenant
from apps.groups.models import Group
from apps.mock_tests.models import MockTest
from apps.core.serializers import UserSummarySerializer
from apps.groups.models import GroupMembership


class GroupSummarySerializer(serializers.ModelSerializer):
    """Serializer for Group summary."""
    
    class Meta:
        model = Group
        fields = ['id', 'name']


class ExamAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for ExamAssignment model."""
    mock_test = serializers.PrimaryKeyRelatedField(
        queryset=MockTest.objects.none(),  # Set in __init__
        required=True,
        help_text="MockTest (must be PUBLISHED)",
    )
    assigned_group_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        allow_empty=True,
        help_text="List of Group UUIDs to assign this exam to",
    )
    assigned_groups = GroupSummarySerializer(many=True, read_only=True)
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = ExamAssignment
        fields = [
            "id", "title", "description", "mock_test", "status",
            "estimated_start_time", "is_published", "assigned_group_ids",
            "assigned_groups", "created_by_id", "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "created_at", "updated_at", "created_by", "assigned_groups",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.mock_tests.models import MockTest
        self.fields["mock_test"].queryset = MockTest.objects.filter(
            status=MockTest.Status.PUBLISHED,
            deleted_at__isnull=True,
        )

    @extend_schema_field(serializers.DictField(allow_null=True, help_text="Creator info"))
    def get_created_by(self, obj):
        """Get user from user_map (no schema switch in serializer loop)."""
        if not obj.created_by_id:
            return None
        user_map = self.context.get("user_map")
        if user_map is not None:
            user = user_map.get(obj.created_by_id)
            if user:
                return UserSummarySerializer.from_user(user)
        return None

    def validate(self, attrs):
        """Validate the entire object using service function."""
        attrs = super().validate(attrs)
        
        mock_test = attrs.get('mock_test') or (self.instance.mock_test if self.instance else None)
        group_ids = attrs.get('assigned_group_ids', [])
        
        if not mock_test:
            raise serializers.ValidationError({
                "mock_test": "MockTest is required."
            })

        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if user and user.role == "TEACHER" and group_ids:
            teaching_group_ids = set(
                GroupMembership.objects.filter(
                    user_id=user.id,
                    role_in_group="TEACHER",
                ).values_list("group_id", flat=True)
            )
            requested_group_ids = set(group_ids)
            if not requested_group_ids.issubset(teaching_group_ids):
                raise serializers.ValidationError({
                    "assigned_group_ids": "Teachers can only assign groups they teach."
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

    @extend_schema_field(serializers.ListField(child=serializers.DictField(), help_text="Assigned mock tests"))
    def get_mock_tests(self, obj):
        """Get list of assigned MockTests."""
        from apps.mock_tests.serializers import MockTestSerializer
        return [
            {"id": str(mt.id), "title": mt.title, "level": mt.level}
            for mt in obj.mock_tests.all()
        ]

    @extend_schema_field(serializers.ListField(child=serializers.DictField(), help_text="Assigned quizzes"))
    def get_quizzes(self, obj):
        """Get list of assigned Quizzes."""
        return [
            {"id": str(q.id), "title": q.title, "description": q.description}
            for q in obj.quizzes.all()
        ]

    @extend_schema_field(serializers.DictField(allow_null=True, help_text="Creator info"))
    def get_created_by(self, obj):
        """Get user from user_map (no schema switch in serializer loop)."""
        if not obj.created_by_id:
            return None
        user_map = self.context.get("user_map")
        if user_map is not None:
            user = user_map.get(obj.created_by_id)
            if user:
                return UserSummarySerializer.from_user(user)
        return None

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

        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if user and user.role == "TEACHER" and group_ids:
            teaching_group_ids = set(
                GroupMembership.objects.filter(
                    user_id=user.id,
                    role_in_group="TEACHER",
                ).values_list("group_id", flat=True)
            )
            requested_group_ids = set(group_ids)
            if not requested_group_ids.issubset(teaching_group_ids):
                raise serializers.ValidationError({
                    "assigned_group_ids": "Teachers can only assign groups they teach."
                })
        
        # Validate users belong to current center (strict: with_public_schema in service)
        request = self.context.get("request")
        tenant_center_id = getattr(request.user, "center_id", None) if request and getattr(request, "user", None) else None
        if user_ids:
            if not tenant_center_id:
                raise serializers.ValidationError({
                    "assigned_user_ids": "Center context required to assign users."
                })
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


def _submission_status_display(submission_status):
    """Map Submission.Status to student-facing status."""
    from apps.attempts.models import Submission
    if not submission_status:
        return "Not Started"
    if submission_status == Submission.Status.GRADED:
        return "Completed"
    if submission_status in (Submission.Status.STARTED, Submission.Status.SUBMITTED):
        return "In Progress"
    return "Not Started"


def _get_submissions_map_for_homework(homework, user_id):
    """
    Single batch query: all submissions for this homework and user.
    Returns {"mock_test": {mock_test_id: status}, "quiz": {quiz_id: status}}.
    """
    if not user_id:
        return {"mock_test": {}, "quiz": {}}
    from apps.attempts.models import Submission
    subs = Submission.objects.filter(
        homework_assignment=homework,
        user_id=user_id,
    ).values("mock_test_id", "quiz_id", "status")
    by_mock_test = {}
    by_quiz = {}
    for s in subs:
        if s["mock_test_id"]:
            by_mock_test[s["mock_test_id"]] = s["status"]
        if s["quiz_id"]:
            by_quiz[s["quiz_id"]] = s["status"]
    return {"mock_test": by_mock_test, "quiz": by_quiz}


class HomeworkDetailSerializer(serializers.ModelSerializer):
    """
    Detail serializer for HomeworkAssignment (retrieve). Shows each assigned
    MockTest/Quiz with **Student's Current Status**: Not Started, In Progress, Completed
    (from attempts.Submission). One batch query for submissions (zero N+1).
    """
    mock_tests = serializers.SerializerMethodField()
    quizzes = serializers.SerializerMethodField()
    assigned_groups = GroupSummarySerializer(many=True, read_only=True)
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = HomeworkAssignment
        fields = [
            "id", "title", "description", "deadline",
            "mock_tests", "quizzes", "assigned_groups",
            "show_results_immediately", "created_by_id", "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    @extend_schema_field(serializers.DictField(allow_null=True, help_text="Creator info"))
    def get_created_by(self, obj):
        if not obj.created_by_id:
            return None
        user_map = self.context.get("user_map")
        if user_map is not None:
            user = user_map.get(obj.created_by_id)
            if user:
                return UserSummarySerializer.from_user(user)
        return None

    def to_representation(self, instance):
        request = self.context.get("request")
        user_id = request.user.id if request and getattr(request, "user", None) else None
        self._submissions_map = _get_submissions_map_for_homework(instance, user_id)
        return super().to_representation(instance)

    @extend_schema_field(serializers.ListField(child=serializers.DictField(), help_text="Assigned mock tests with student status"))
    def get_mock_tests(self, obj):
        subs_map = getattr(self, "_submissions_map", None)
        if subs_map is None:
            request = self.context.get("request")
            user_id = request.user.id if request and getattr(request, "user", None) else None
            subs_map = _get_submissions_map_for_homework(obj, user_id)
        by_mt = subs_map.get("mock_test", {})
        return [
            {
                "id": str(mt.id),
                "title": mt.title,
                "level": mt.level,
                "description": getattr(mt, "description", "") or "",
                "status": _submission_status_display(by_mt.get(mt.id)),
                "type": "mock_test",
            }
            for mt in obj.mock_tests.all()
        ]

    @extend_schema_field(serializers.ListField(child=serializers.DictField(), help_text="Assigned quizzes with student status"))
    def get_quizzes(self, obj):
        subs_map = getattr(self, "_submissions_map", None)
        if subs_map is None:
            request = self.context.get("request")
            user_id = request.user.id if request and getattr(request, "user", None) else None
            subs_map = _get_submissions_map_for_homework(obj, user_id)
        by_quiz = subs_map.get("quiz", {})
        return [
            {
                "id": str(q.id),
                "title": q.title,
                "description": q.description or "",
                "status": _submission_status_display(by_quiz.get(q.id)),
                "type": "quiz",
            }
            for q in obj.quizzes.all()
        ]
