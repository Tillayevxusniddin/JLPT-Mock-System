# apps/mock_tests/serializers.py
"""
Mock tests serializers. Published-protection logic (validate_mock_test_editable,
validate_child_object_editable) is applied in validate() and documented in
apps.mock_tests.swagger. correct_option_index is auto-calculated from options.
"""
from django.db import transaction
from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import MockTest, TestSection, QuestionGroup, Question, Quiz, QuizQuestion
from .services import validate_mock_test_editable, validate_child_object_editable
from apps.core.serializers import UserSummarySerializer


class QuestionSerializer(serializers.ModelSerializer):
    """Serializer for Question model with options JSONField validation."""
    
    class Meta:
        model = Question
        fields = [
            "id", "group", "text", "question_number", "image", "audio_file",
            "score", "order", "options", "correct_option_index", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "correct_option_index", "created_at", "updated_at"]

    def validate_options(self, value):
        """Validate the options JSONField."""
        if not isinstance(value, list):
            raise serializers.ValidationError("Options must be a list.")
        
        if len(value) == 0:
            raise serializers.ValidationError("At least one option is required.")
        
        # Validate each option has required fields
        for idx, opt in enumerate(value):
            if not isinstance(opt, dict):
                raise serializers.ValidationError(f"Option at index {idx} must be a dictionary.")
            if "text" not in opt:
                raise serializers.ValidationError(f"Option at index {idx} must have a 'text' field.")
            if "is_correct" not in opt:
                raise serializers.ValidationError(f"Option at index {idx} must have an 'is_correct' field.")
            if not isinstance(opt.get("is_correct"), bool):
                raise serializers.ValidationError(f"Option at index {idx} 'is_correct' must be a boolean.")
        
        # Check exactly one option is correct
        correct_count = sum(1 for opt in value if opt.get("is_correct", False))
        if correct_count != 1:
            raise serializers.ValidationError(
                f"There must be exactly one correct option. Found {correct_count}."
            )
        
        return value

    def validate(self, attrs):
        """Validate the entire object, including parent MockTest status."""
        attrs = super().validate(attrs)
        
        # For updates, check if parent MockTest is published
        if self.instance:
            try:
                validate_child_object_editable(self.instance)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"detail": str(e)})
        
        # For creates, we need to check the group's parent MockTest
        if not self.instance and "group" in attrs:
            group = attrs["group"]
            try:
                validate_child_object_editable(group)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"detail": str(e)})
        
        return attrs

    def _set_correct_option_index(self, validated_data):
        options = validated_data.get("options")
        if options:
            for idx, opt in enumerate(options):
                if opt.get("is_correct", False):
                    validated_data["correct_option_index"] = idx
                    break
        return validated_data

    def create(self, validated_data):
        validated_data = self._set_correct_option_index(validated_data)
        with transaction.atomic():
            return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data = self._set_correct_option_index(validated_data)
        with transaction.atomic():
            return super().update(instance, validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.role in ("STUDENT", "GUEST"):
            data.pop("correct_option_index", None)
            options = data.get("options")
            if isinstance(options, list):
                data["options"] = [
                    {k: v for k, v in opt.items() if k != "is_correct"}
                    if isinstance(opt, dict) else opt
                    for opt in options
                ]
        return data


class QuestionGroupSerializer(serializers.ModelSerializer):
    """Serializer for QuestionGroup model."""
    questions = QuestionSerializer(many=True, read_only=True)
    
    class Meta:
        model = QuestionGroup
        fields = [
            "id", "section", "mondai_number", "title", "instruction",
            "reading_text", "audio_file", "image", "order", "questions",
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "questions"]

    def validate(self, attrs):
        """Validate the entire object, including parent MockTest status."""
        attrs = super().validate(attrs)
        
        # For updates, check if parent MockTest is published
        if self.instance:
            try:
                validate_child_object_editable(self.instance)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"detail": str(e)})
        
        # For creates, check the section's parent MockTest
        if not self.instance and "section" in attrs:
            section = attrs["section"]
            try:
                validate_child_object_editable(section)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"detail": str(e)})
        
        return attrs


class TestSectionSerializer(serializers.ModelSerializer):
    """Serializer for TestSection model."""
    question_groups = QuestionGroupSerializer(many=True, read_only=True)
    
    class Meta:
        model = TestSection
        fields = [
            "id", "mock_test", "name", "section_type", "duration",
            "order", "total_score", "question_groups", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "question_groups"]

    def validate(self, attrs):
        """Validate the entire object, including parent MockTest status."""
        attrs = super().validate(attrs)
        
        # For updates, check if parent MockTest is published
        if self.instance:
            try:
                validate_child_object_editable(self.instance)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"detail": str(e)})
        
        # For creates, check the mock_test status
        if not self.instance and "mock_test" in attrs:
            mock_test = attrs["mock_test"]
            try:
                validate_mock_test_editable(mock_test)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"detail": str(e)})
        
        return attrs


class MockTestSerializer(serializers.ModelSerializer):
    """Serializer for MockTest model."""
    created_by = serializers.SerializerMethodField()
    sections = TestSectionSerializer(many=True, read_only=True)
    
    class Meta:
        model = MockTest
        fields = [
            "id", "title", "level", "description", "status", "created_by_id",
            "created_by", "pass_score", "total_score", "sections",
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "sections"]

    def get_created_by(self, obj):
        """Get user from user_map (no schema switch); created_by_id is stored as user.id (int)."""
        if not obj.created_by_id:
            return None
        user_map = self.context.get("user_map")
        if user_map is not None:
            uid = obj.created_by_id
            if hasattr(uid, "__int__"):
                try:
                    uid = int(uid)
                except (ValueError, OverflowError):
                    pass
            user = user_map.get(uid)
            if user:
                return UserSummarySerializer.from_user(user)
        return UserSummarySerializer.from_user(obj.created_by) if getattr(obj, "created_by", None) else None

    def validate(self, attrs):
        """Validate the entire object, including published status check."""
        attrs = super().validate(attrs)
        
        # For updates, check if MockTest is published
        if self.instance:
            try:
                validate_mock_test_editable(self.instance)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"detail": str(e)})
        
        return attrs


class QuizQuestionSerializer(serializers.ModelSerializer):
    """Serializer for QuizQuestion model with options JSONField validation."""
    
    class Meta:
        model = QuizQuestion
        fields = [
            "id", "quiz", "text", "question_type", "image", "duration",
            "points", "order", "options", "correct_option_index",
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "correct_option_index", "created_at", "updated_at"]

    def validate_options(self, value):
        """Validate the options JSONField."""
        if not isinstance(value, list):
            raise serializers.ValidationError("Options must be a list.")
        
        if len(value) == 0:
            raise serializers.ValidationError("At least one option is required.")
        
        # Validate each option
        for idx, opt in enumerate(value):
            if not isinstance(opt, dict):
                raise serializers.ValidationError(f"Option at index {idx} must be a dictionary.")
            if "text" not in opt:
                raise serializers.ValidationError(f"Option at index {idx} must have a 'text' field.")
            if "is_correct" not in opt:
                raise serializers.ValidationError(f"Option at index {idx} must have an 'is_correct' field.")
            if not isinstance(opt.get("is_correct"), bool):
                raise serializers.ValidationError(f"Option at index {idx} 'is_correct' must be a boolean.")
        
        # Check exactly one option is correct
        correct_count = sum(1 for opt in value if opt.get("is_correct", False))
        if correct_count != 1:
            raise serializers.ValidationError(
                f"There must be exactly one correct option. Found {correct_count}."
            )
        
        return value

    def _set_correct_option_index(self, validated_data):
        options = validated_data.get("options")
        if options:
            for idx, opt in enumerate(options):
                if opt.get("is_correct", False):
                    validated_data["correct_option_index"] = idx
                    break
        return validated_data

    def create(self, validated_data):
        validated_data = self._set_correct_option_index(validated_data)
        with transaction.atomic():
            return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data = self._set_correct_option_index(validated_data)
        with transaction.atomic():
            return super().update(instance, validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.role in ("STUDENT", "GUEST"):
            data.pop("correct_option_index", None)
            options = data.get("options")
            if isinstance(options, list):
                data["options"] = [
                    {k: v for k, v in opt.items() if k != "is_correct"}
                    if isinstance(opt, dict) else opt
                    for opt in options
                ]
        return data


class QuizSerializer(serializers.ModelSerializer):
    """Serializer for Quiz model."""
    created_by = serializers.SerializerMethodField()
    questions = QuizQuestionSerializer(many=True, read_only=True)
    
    class Meta:
        model = Quiz
        fields = [
            "id", "title", "description", "created_by_id", "created_by",
            "is_active", "default_question_duration", "questions",
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "questions"]

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
