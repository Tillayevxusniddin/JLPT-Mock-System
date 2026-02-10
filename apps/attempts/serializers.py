# apps/attempts/serializers.py
"""
Attempts serializers. Exam/quiz paper serializers are sanitized (no correct_option_index
or is_correct). Snapshot serializers include full structure for historical integrity.
Documented in apps/attempts/swagger.py.
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Submission
from apps.core.serializers import user_display_from_map
from apps.mock_tests.models import MockTest, TestSection, QuestionGroup, Question, Quiz, QuizQuestion


class ExamQuestionSerializer(serializers.ModelSerializer):
    """
    Question serializer for exam paper (SECURITY: excludes correct answers).
    
    This serializer is used when returning the exam paper to students.
    It MUST NOT include:
    - correct_option_index
    - is_correct flags in options
    
    Note: correct_option_index is excluded via fields list (not in fields).
    """
    # Override options to exclude is_correct flag
    options = serializers.SerializerMethodField()
    
    class Meta:
        model = Question
        fields = [
            "id", "group", "text", "question_number", "image", "audio_file",
            "score", "order", "options", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_options(self, obj):
        """
        Return options without is_correct flag for security.
        """
        if not obj.options:
            return []
        
        # Remove is_correct flag from each option
        sanitized_options = []
        for opt in obj.options:
            sanitized_opt = {k: v for k, v in opt.items() if k != 'is_correct'}
            sanitized_options.append(sanitized_opt)
        
        return sanitized_options


class ExamQuestionGroupSerializer(serializers.ModelSerializer):
    """QuestionGroup serializer for exam paper."""
    questions = ExamQuestionSerializer(many=True, read_only=True)
    
    class Meta:
        model = QuestionGroup
        fields = [
            "id", "section", "mondai_number", "title", "instruction",
            "reading_text", "audio_file", "image", "order", "questions",
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "questions"]


class ExamTestSectionSerializer(serializers.ModelSerializer):
    """TestSection serializer for exam paper."""
    question_groups = ExamQuestionGroupSerializer(many=True, read_only=True)
    
    class Meta:
        model = TestSection
        fields = [
            "id", "mock_test", "name", "section_type", "duration",
            "order", "total_score", "question_groups", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "question_groups"]


class ExamPaperSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for MockTest as an exam paper.
    
    This serializer returns the entire MockTest structure (Sections -> Groups -> Questions -> Options)
    WITHOUT correct answers. Used when a student starts an exam.
    
    SECURITY: This serializer explicitly excludes:
    - correct_option_index from Question
    - is_correct flags from options JSONField
    """
    sections = ExamTestSectionSerializer(many=True, read_only=True)
    
    class Meta:
        model = MockTest
        fields = [
            "id", "title", "level", "description", "pass_score", "total_score",
            "sections", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "sections"]
        # Explicitly exclude status and created_by_id (not needed for exam paper)


class QuizQuestionPaperSerializer(serializers.ModelSerializer):
    """
    QuizQuestion serializer for quiz paper (SECURITY: excludes correct answers).
    
    Note: correct_option_index is excluded via fields list (not in fields).
    """
    options = serializers.SerializerMethodField()
    
    class Meta:
        model = QuizQuestion
        fields = [
            "id", "quiz", "text", "question_type", "image", "duration",
            "points", "order", "options", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
    
    def get_options(self, obj):
        """Return options without is_correct flag for security."""
        if not obj.options:
            return []
        sanitized_options = []
        for opt in obj.options:
            sanitized_opt = {k: v for k, v in opt.items() if k != 'is_correct'}
            sanitized_options.append(sanitized_opt)
        return sanitized_options


class QuizPaperSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for Quiz as a homework paper.
    
    SECURITY: Excludes correct_option_index and is_correct flags.
    """
    questions = QuizQuestionPaperSerializer(many=True, read_only=True)
    
    class Meta:
        model = Quiz
        fields = [
            "id", "title", "description", "default_question_duration",
            "questions", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "questions"]


# ============================================================================
# FULL SNAPSHOT SERIALIZERS (INCLUDES CORRECT ANSWERS)
# These are used to preserve the complete test state for historical integrity
# ============================================================================

class FullQuestionSnapshotSerializer(serializers.ModelSerializer):
    """
    Full Question serializer WITH correct answers for snapshot.
    
    This is used internally to preserve test state at time of grading.
    """
    class Meta:
        model = Question
        fields = [
            "id", "group", "text", "question_number", "image", "audio_file",
            "score", "order", "options", "correct_option_index",
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class FullQuestionGroupSnapshotSerializer(serializers.ModelSerializer):
    """QuestionGroup serializer for snapshot (includes correct answers)."""
    questions = FullQuestionSnapshotSerializer(many=True, read_only=True)
    
    class Meta:
        model = QuestionGroup
        fields = [
            "id", "section", "mondai_number", "title", "instruction",
            "reading_text", "audio_file", "image", "order", "questions",
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "questions"]


class FullTestSectionSnapshotSerializer(serializers.ModelSerializer):
    """TestSection serializer for snapshot (includes correct answers)."""
    question_groups = FullQuestionGroupSnapshotSerializer(many=True, read_only=True)
    
    class Meta:
        model = TestSection
        fields = [
            "id", "mock_test", "name", "section_type", "duration",
            "order", "total_score", "question_groups", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "question_groups"]


class FullMockTestSnapshotSerializer(serializers.ModelSerializer):
    """
    Full MockTest serializer WITH correct answers for snapshot.
    
    This serializer preserves the complete state of a MockTest including:
    - All sections, groups, questions
    - Correct answers (correct_option_index and is_correct flags)
    - All metadata
    
    Used internally to create snapshots for historical integrity.
    """
    sections = FullTestSectionSnapshotSerializer(many=True, read_only=True)
    
    class Meta:
        model = MockTest
        fields = [
            "id", "title", "level", "description", "status", "pass_score", "total_score",
            "sections", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "sections"]


class FullQuizQuestionSnapshotSerializer(serializers.ModelSerializer):
    """
    Full QuizQuestion serializer WITH correct answers for snapshot.
    """
    class Meta:
        model = QuizQuestion
        fields = [
            "id", "quiz", "text", "question_type", "image", "duration",
            "points", "order", "options", "correct_option_index",
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class FullQuizSnapshotSerializer(serializers.ModelSerializer):
    """
    Full Quiz serializer WITH correct answers for snapshot.
    
    This serializer preserves the complete state of a Quiz including:
    - All questions
    - Correct answers (correct_option_index and is_correct flags)
    - All metadata
    
    Used internally to create snapshots for historical integrity.
    """
    questions = FullQuizQuestionSnapshotSerializer(many=True, read_only=True)
    
    class Meta:
        model = Quiz
        fields = [
            "id", "title", "description", "is_active", "default_question_duration",
            "questions", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "questions"]


class SubmissionAnswerSerializer(serializers.Serializer):
    """
    Serializer for student answers submission.
    
    Expected format: {"question_uuid": selected_option_index}
    Example: {"550e8400-e29b-41d4-a716-446655440000": 2, "660e8400-e29b-41d4-a716-446655440001": 0}
    """
    def to_internal_value(self, data):
        """
        Validate that data is a dict with UUID keys and integer values.
        """
        if not isinstance(data, dict):
            raise serializers.ValidationError("Answers must be a dictionary.")
        
        validated_data = {}
        for question_id_str, option_index in data.items():
            try:
                # Validate question_id is a valid UUID string
                import uuid
                question_uuid = uuid.UUID(question_id_str)
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    f"Invalid question ID format: {question_id_str}. Must be a valid UUID."
                )
            
            # Validate option_index is an integer
            if not isinstance(option_index, int):
                try:
                    option_index = int(option_index)
                except (ValueError, TypeError):
                    raise serializers.ValidationError(
                        f"Option index for question {question_id_str} must be an integer."
                    )
            
            if option_index < 0:
                raise serializers.ValidationError(
                    f"Option index for question {question_id_str} must be non-negative."
                )
            
            validated_data[str(question_uuid)] = option_index
        
        return validated_data


class SubmissionResultSerializer(serializers.ModelSerializer):
    """
    Serializer for showing submission results (exam/homework) after published.
    Includes score, results breakdown, JLPT pass/fail, time_taken, percentage for dashboard.
    """
    assignment_title = serializers.SerializerMethodField()
    assignment_type = serializers.SerializerMethodField()
    mock_test_title = serializers.SerializerMethodField()
    mock_test_level = serializers.SerializerMethodField()
    time_taken_seconds = serializers.SerializerMethodField()
    percentage = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = [
            "id", "user_id", "status", "started_at", "completed_at",
            "score", "results", "assignment_title", "assignment_type",
            "mock_test_title", "mock_test_level",
            "time_taken_seconds", "percentage",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "user_id", "status", "started_at", "completed_at",
            "score", "results", "created_at", "updated_at",
        ]

    def get_assignment_title(self, obj):
        """Get assignment title."""
        if obj.exam_assignment:
            return obj.exam_assignment.title
        elif obj.homework_assignment:
            return obj.homework_assignment.title
        return None

    def get_assignment_type(self, obj):
        """Get assignment type."""
        if obj.exam_assignment:
            return "exam"
        elif obj.homework_assignment:
            return "homework"
        return None

    def get_mock_test_title(self, obj):
        resource = obj.resource
        if resource and hasattr(resource, "title"):
            return resource.title
        return None

    def get_mock_test_level(self, obj):
        resource = obj.resource
        if resource and hasattr(resource, "level"):
            return resource.level
        return None

    def get_time_taken_seconds(self, obj):
        """Seconds between started_at and completed_at (for dashboard)."""
        if obj.started_at and obj.completed_at:
            delta = obj.completed_at - obj.started_at
            return max(0, int(delta.total_seconds()))
        return None

    def get_percentage(self, obj):
        """Percentage of max score from results JSON (for dashboard)."""
        if not obj.results or not isinstance(obj.results, dict):
            return None
        total = obj.results.get("total_score")
        max_s = obj.results.get("max_score")
        if max_s and max_s > 0 and total is not None:
            return round(float(total) / float(max_s) * 100, 2)
        jlpt = obj.results.get("jlpt_result") or {}
        pass_mark = jlpt.get("pass_mark")
        if pass_mark and pass_mark > 0 and total is not None:
            return round(float(total) / float(pass_mark) * 100, 2)
        return None


class SubmissionSerializer(serializers.ModelSerializer):
    """
    Standard serializer for Submission (teachers/admins list/retrieve).
    student_display is populated from user_map in context (batch-fetched, no N+1).
    """
    assignment_title = serializers.SerializerMethodField()
    assignment_type = serializers.SerializerMethodField()
    student_display = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = [
            "id", "user_id", "student_display", "exam_assignment", "homework_assignment",
            "status", "started_at", "completed_at", "score", "results",
            "assignment_title", "assignment_type", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "user_id", "status", "started_at", "completed_at",
            "score", "results", "created_at", "updated_at",
        ]

    @extend_schema_field(serializers.CharField(allow_null=True, help_text="Assignment title"))
    def get_assignment_title(self, obj):
        if obj.exam_assignment:
            return obj.exam_assignment.title
        if obj.homework_assignment:
            return obj.homework_assignment.title
        return None

    @extend_schema_field(serializers.ChoiceField(choices=["exam", "homework"], allow_null=True))
    def get_assignment_type(self, obj):
        if obj.exam_assignment:
            return "exam"
        if obj.homework_assignment:
            return "homework"
        return None

    @extend_schema_field(serializers.CharField(help_text="Student display name"))
    def get_student_display(self, obj):
        user_map = self.context.get("user_map")
        return user_display_from_map(user_map, obj.user_id)
