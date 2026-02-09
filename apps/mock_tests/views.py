# apps/mock_tests/views.py
"""
Mock tests app API views. All OpenAPI schemas, published-protection docs, and
hierarchy descriptions are in apps.mock_tests.swagger; views are thin and only
apply decorators from that module. Published lock is enforced in serializers
(validate) and perform_destroy (services.validate_*).
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Prefetch

from .models import MockTest, TestSection, QuestionGroup, Question, Quiz, QuizQuestion
from .serializers import (
    MockTestSerializer,
    TestSectionSerializer,
    QuestionGroupSerializer,
    QuestionSerializer,
    QuizSerializer,
    QuizQuestionSerializer,
)
from .permissions import IsMockTestAdminOrTeacherOrReadOnly
from .services import (
    validate_mock_test_editable,
    validate_child_object_editable,
    PUBLISHED_TEST_EDIT_MESSAGE,
    soft_delete_mock_test_tree,
)
from .swagger import (
    mock_test_viewset_schema,
    test_section_viewset_schema,
    question_group_viewset_schema,
    question_viewset_schema,
    quiz_viewset_schema,
    quiz_question_viewset_schema,
)
from apps.core.tenant_utils import get_current_schema, with_public_schema
from apps.centers.models import Center


def _guard_queryset_by_center(queryset, user):
    """Defense-in-depth tenant guard using user.center_id vs current schema."""
    if not getattr(user, "center_id", None):
        return queryset.none()
    schema_name = get_current_schema() or "public"

    def fetch_center_schema():
        return Center.objects.filter(id=user.center_id).values_list("schema_name", flat=True).first()

    center_schema = with_public_schema(fetch_center_schema)
    if not center_schema or center_schema != schema_name:
        return queryset.none()
    return queryset


@mock_test_viewset_schema
class MockTestViewSet(viewsets.ModelViewSet):
    serializer_class = MockTestSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = MockTest.objects.all()

    def get_queryset(self):
        """Filter queryset based on user role."""
        if getattr(self, 'swagger_fake_view', False):
            return MockTest.objects.none()
        
        user = self.request.user
        queryset = MockTest.objects.all().order_by("-created_at")
        queryset = _guard_queryset_by_center(queryset, user)
        if user.role in ("CENTER_ADMIN", "TEACHER"):
            return queryset
        if user.role in ("STUDENT", "GUEST"):
            return queryset.filter(status=MockTest.Status.PUBLISHED)
        return MockTest.objects.none()

    def list(self, request, *args, **kwargs):
        """
        List endpoint with standard filtering. User optimization deferred to serializer if needed.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Set created_by_id on create (BigIntegerField stores user.id)."""
        serializer.save(created_by_id=self.request.user.id)

    def perform_update(self, serializer):
        """Save; serializer already validates published lock and returns 400."""
        serializer.save()

    def perform_destroy(self, instance):
        """Block hard delete when test is published; return 400."""
        from django.core.exceptions import ValidationError as DjangoValidationError
        from rest_framework.exceptions import ValidationError as DRFValidationError
        try:
            validate_mock_test_editable(instance)
        except DjangoValidationError:
            raise DRFValidationError({"detail": PUBLISHED_TEST_EDIT_MESSAGE})
        soft_delete_mock_test_tree(instance)

    def retrieve(self, request, *args, **kwargs):
        """
        Retrieve single mock test with optimized prefetch for sections/groups/questions.
        Note: created_by user_map optimization is deferred to serializer field if needed.
        """
        queryset = self.get_queryset().prefetch_related(
            Prefetch(
                "sections",
                queryset=TestSection.objects.order_by("order").prefetch_related(
                    Prefetch(
                        "question_groups",
                        queryset=QuestionGroup.objects.order_by("order").prefetch_related(
                            Prefetch(
                                "questions",
                                queryset=Question.objects.order_by("order"),
                            )
                        ),
                    )
                ),
            )
        )
        instance = queryset.get(pk=kwargs["pk"])
        serializer = self.get_serializer(instance, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, pk=None):
        mock_test = self.get_object()
        user = request.user
        
        # Check permissions
        if user.role == "CENTER_ADMIN":
            pass  # Full access
        elif user.role == "TEACHER":
            if mock_test.created_by_id is not None:
                uid = mock_test.created_by_id
                if hasattr(uid, "__int__"):
                    try:
                        uid = int(uid)
                    except (ValueError, OverflowError):
                        uid = None
                if uid != user.id:
                    return Response(
                        {"detail": "Only the creator or center admin can publish/unpublish this test."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
        else:
            return Response(
                {"detail": "Only center admins or teachers can publish/unpublish tests."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Toggle status
        if mock_test.status == MockTest.Status.PUBLISHED:
            mock_test.status = MockTest.Status.DRAFT
            action = "unpublished"
        else:
            mock_test.status = MockTest.Status.PUBLISHED
            action = "published"
        
        mock_test.save(update_fields=['status'])
        
        serializer = self.get_serializer(mock_test)
        return Response({
            "detail": f"MockTest {action} successfully.",
            "data": serializer.data
        })

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request, pk=None):
        source = self.get_object()
        user = request.user

        if user.role not in ("CENTER_ADMIN", "TEACHER"):
            return Response(
                {"detail": "Only center admins or teachers can clone tests."},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            cloned = MockTest.objects.create(
                title=f"{source.title} (Copy)",
                level=source.level,
                description=source.description,
                status=MockTest.Status.DRAFT,
                created_by_id=user.id,
                pass_score=source.pass_score,
                total_score=source.total_score,
            )

            section_map = {}
            for section in source.sections.all().order_by("order"):
                new_section = TestSection.objects.create(
                    mock_test=cloned,
                    name=section.name,
                    section_type=section.section_type,
                    duration=section.duration,
                    order=section.order,
                    total_score=section.total_score,
                )
                section_map[section.id] = new_section

            group_map = {}
            for group in QuestionGroup.objects.filter(section__mock_test=source).order_by("section", "order"):
                new_group = QuestionGroup.objects.create(
                    section=section_map[group.section_id],
                    mondai_number=group.mondai_number,
                    title=group.title,
                    instruction=group.instruction,
                    reading_text=group.reading_text,
                    audio_file=group.audio_file,
                    image=group.image,
                    order=group.order,
                )
                group_map[group.id] = new_group

            for question in Question.objects.filter(group__section__mock_test=source).order_by("group", "order"):
                Question.objects.create(
                    group=group_map[question.group_id],
                    text=question.text,
                    question_number=question.question_number,
                    image=question.image,
                    audio_file=question.audio_file,
                    score=question.score,
                    order=question.order,
                    options=question.options,
                    correct_option_index=question.correct_option_index,
                )

        serializer = self.get_serializer(cloned, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@test_section_viewset_schema
class TestSectionViewSet(viewsets.ModelViewSet):
    serializer_class = TestSectionSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = TestSection.objects.all()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TestSection.objects.none()
        
        queryset = TestSection.objects.select_related('mock_test').order_by('order')
        
        # Filter by mock_test if provided
        mock_test_id = self.request.query_params.get('mock_test', None)
        if mock_test_id:
            queryset = queryset.filter(mock_test_id=mock_test_id)
        
        user = self.request.user
        queryset = _guard_queryset_by_center(queryset, user)
        
        # For STUDENT/GUEST, only show sections of published MockTests
        if user.role in ("STUDENT", "GUEST"):
            queryset = queryset.filter(mock_test__status=MockTest.Status.PUBLISHED)
        
        return queryset

    def perform_create(self, serializer):
        mock_test = serializer.validated_data.get("mock_test")
        if mock_test:
            try:
                validate_mock_test_editable(mock_test)
            except Exception as e:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"detail": str(e)})
        serializer.save()

    def perform_destroy(self, instance):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from rest_framework.exceptions import ValidationError as DRFValidationError
        try:
            validate_child_object_editable(instance)
        except DjangoValidationError:
            raise DRFValidationError({"detail": PUBLISHED_TEST_EDIT_MESSAGE})
        instance.delete()


@question_group_viewset_schema
class QuestionGroupViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionGroupSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = QuestionGroup.objects.all()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return QuestionGroup.objects.none()
        
        queryset = QuestionGroup.objects.select_related(
            'section', 'section__mock_test'
        ).order_by('section', 'order')
        
        # Filter by section if provided
        section_id = self.request.query_params.get('section', None)
        if section_id:
            queryset = queryset.filter(section_id=section_id)
        
        # Filter by mock_test if provided
        mock_test_id = self.request.query_params.get('mock_test', None)
        if mock_test_id:
            queryset = queryset.filter(section__mock_test_id=mock_test_id)
        
        user = self.request.user
        queryset = _guard_queryset_by_center(queryset, user)
        
        # For STUDENT/GUEST, only show groups of published MockTests
        if user.role in ("STUDENT", "GUEST"):
            queryset = queryset.filter(section__mock_test__status=MockTest.Status.PUBLISHED)
        
        return queryset

    def perform_create(self, serializer):
        section = serializer.validated_data.get("section")
        if section:
            try:
                validate_mock_test_editable(section.mock_test)
            except Exception as e:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"detail": str(e)})
        serializer.save()

    def perform_destroy(self, instance):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from rest_framework.exceptions import ValidationError as DRFValidationError
        try:
            validate_child_object_editable(instance)
        except DjangoValidationError:
            raise DRFValidationError({"detail": PUBLISHED_TEST_EDIT_MESSAGE})
        instance.delete()


@question_viewset_schema
class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = Question.objects.all()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Question.objects.none()
        
        queryset = Question.objects.select_related(
            'group', 'group__section', 'group__section__mock_test'
        ).order_by('group', 'order')
        
        # Filter by group if provided
        group_id = self.request.query_params.get('group', None)
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        
        # Filter by section if provided
        section_id = self.request.query_params.get('section', None)
        if section_id:
            queryset = queryset.filter(group__section_id=section_id)
        
        # Filter by mock_test if provided
        mock_test_id = self.request.query_params.get('mock_test', None)
        if mock_test_id:
            queryset = queryset.filter(group__section__mock_test_id=mock_test_id)
        
        user = self.request.user
        queryset = _guard_queryset_by_center(queryset, user)
        
        # For STUDENT/GUEST, only show questions of published MockTests
        if user.role in ("STUDENT", "GUEST"):
            queryset = queryset.filter(group__section__mock_test__status=MockTest.Status.PUBLISHED)
        
        return queryset

    def perform_create(self, serializer):
        group = serializer.validated_data.get("group")
        if group:
            try:
                validate_mock_test_editable(group.section.mock_test)
            except Exception as e:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"detail": str(e)})
        serializer.save()

    def perform_destroy(self, instance):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from rest_framework.exceptions import ValidationError as DRFValidationError
        try:
            validate_child_object_editable(instance)
        except DjangoValidationError:
            raise DRFValidationError({"detail": PUBLISHED_TEST_EDIT_MESSAGE})
        instance.delete()


@quiz_viewset_schema
class QuizViewSet(viewsets.ModelViewSet):
    serializer_class = QuizSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = Quiz.objects.all()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Quiz.objects.none()
        
        user = self.request.user
        queryset = Quiz.objects.all().order_by('-created_at')
        queryset = _guard_queryset_by_center(queryset, user)
        
        # CENTER_ADMIN and TEACHER: See all Quizzes
        if user.role in ("CENTER_ADMIN", "TEACHER"):
            return queryset
        
        # STUDENT and GUEST: See only active Quizzes
        if user.role in ("STUDENT", "GUEST"):
            return queryset.filter(is_active=True)
        
        return Quiz.objects.none()

    def list(self, request, *args, **kwargs):
        # created_by batch-fetched from public schema (user_map); see swagger QUIZ_LIST_DESC.
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        quizzes = page if page is not None else queryset
        
        # Optimize N+1 for created_by
        user_ids = set()
        for quiz in quizzes:
            if quiz.created_by_id:
                user_ids.add(quiz.created_by_id)
        
        user_map = {}
        if user_ids:
            from apps.core.tenant_utils import with_public_schema
            from apps.authentication.models import User
            
            def fetch_users():
                return {u.id: u for u in User.objects.filter(id__in=user_ids)}
            
            user_map = with_public_schema(fetch_users)
        
        serializer = self.get_serializer(
            quizzes,
            many=True,
            context={'request': request, 'user_map': user_map}
        )
        
        if page is not None:
            return self.get_paginated_response(serializer.data)
        
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(created_by_id=self.request.user.id)


@quiz_question_viewset_schema
class QuizQuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuizQuestionSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = QuizQuestion.objects.all()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return QuizQuestion.objects.none()
        
        queryset = QuizQuestion.objects.select_related('quiz').order_by('order')
        
        # Filter by quiz if provided
        quiz_id = self.request.query_params.get('quiz', None)
        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)
        
        user = self.request.user
        queryset = _guard_queryset_by_center(queryset, user)
        
        # For STUDENT/GUEST, only show questions of active Quizzes
        if user.role in ("STUDENT", "GUEST"):
            queryset = queryset.filter(quiz__is_active=True)
        
        return queryset
