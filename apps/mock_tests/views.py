# apps/mock_tests/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.db import transaction

from .models import MockTest, TestSection, QuestionGroup, Question, Quiz, QuizQuestion
from .serializers import (
    MockTestSerializer, TestSectionSerializer, QuestionGroupSerializer,
    QuestionSerializer, QuizSerializer, QuizQuestionSerializer
)
from .permissions import IsMockTestAdminOrTeacherOrReadOnly
from .services import validate_mock_test_editable, get_parent_mock_test


class MockTestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for MockTest model.
    
    Filtering:
    - Students/Guests: See only PUBLISHED MockTests
    - Admins/Teachers: See all MockTests
    
    Custom Actions:
    - publish: Toggle status between DRAFT and PUBLISHED
    """
    serializer_class = MockTestSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = MockTest.objects.all()

    def get_queryset(self):
        """Filter queryset based on user role."""
        if getattr(self, 'swagger_fake_view', False):
            return MockTest.objects.none()
        
        user = self.request.user
        queryset = MockTest.objects.all().order_by('-created_at')
        
        # CENTER_ADMIN and TEACHER: See all MockTests
        if user.role in ("CENTER_ADMIN", "TEACHER"):
            return queryset
        
        # STUDENT and GUEST: See only PUBLISHED MockTests
        if user.role in ("STUDENT", "GUEST"):
            return queryset.filter(status=MockTest.Status.PUBLISHED)
        
        return MockTest.objects.none()

    def list(self, request, *args, **kwargs):
        """
        Optimized list endpoint to fix N+1 schema switching for 'created_by' field.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        mock_tests = page if page is not None else queryset
        
        # Optimize N+1 for created_by
        user_ids = set()
        for mt in mock_tests:
            if mt.created_by_id:
                # Handle UUIDField to int conversion
                try:
                    user_id = mt.created_by_id
                    if hasattr(user_id, '__int__'):
                        user_id = int(user_id)
                    user_ids.add(user_id)
                except (ValueError, TypeError):
                    pass
        
        user_map = {}
        if user_ids:
            from apps.core.tenant_utils import with_public_schema
            from apps.authentication.models import User
            
            def fetch_users():
                return {u.id: u for u in User.objects.filter(id__in=user_ids)}
            
            user_map = with_public_schema(fetch_users)
        
        serializer = self.get_serializer(
            mock_tests,
            many=True,
            context={'request': request, 'user_map': user_map}
        )
        
        if page is not None:
            return self.get_paginated_response(serializer.data)
        
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Set created_by_id on create."""
        user = self.request.user
        # Note: MockTest.created_by_id is UUIDField but User.id is BigAutoField
        # Convert user.id to UUID format for storage
        import uuid
        try:
            # Create a UUID from the integer user.id
            user_uuid = uuid.UUID(int=user.id)
            serializer.save(created_by_id=user_uuid)
        except (ValueError, OverflowError):
            # Fallback: try storing as string representation
            # This handles edge cases where user.id might be too large
            serializer.save(created_by_id=str(user.id))

    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        """
        Toggle MockTest status between DRAFT and PUBLISHED.
        
        Only CENTER_ADMIN or the creator (for TEACHER) can publish/unpublish.
        """
        mock_test = self.get_object()
        user = request.user
        
        # Check permissions
        if user.role == "CENTER_ADMIN":
            pass  # Full access
        elif user.role == "TEACHER":
            # Check if user is the creator
            if mock_test.created_by_id:
                try:
                    created_by_id = mock_test.created_by_id
                    user_id = user.id
                    
                    # Try various comparison methods
                    is_creator = (
                        created_by_id == user_id or
                        str(created_by_id) == str(user_id) or
                        (hasattr(created_by_id, '__int__') and int(created_by_id) == user_id)
                    )
                    
                    # Try UUID conversion
                    if not is_creator:
                        import uuid
                        try:
                            uuid_from_int = uuid.UUID(int=user_id)
                            is_creator = str(created_by_id) == str(uuid_from_int)
                        except (ValueError, OverflowError):
                            pass
                    
                    if not is_creator:
                        return Response(
                            {"detail": "Only the creator or center admin can publish/unpublish this test."},
                            status=status.HTTP_403_FORBIDDEN
                        )
                except (ValueError, TypeError, AttributeError):
                    return Response(
                        {"detail": "Permission denied."},
                        status=status.HTTP_403_FORBIDDEN
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


class TestSectionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for TestSection model.
    
    Permissions check the parent MockTest's status before allowing modifications.
    """
    serializer_class = TestSectionSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = TestSection.objects.all()

    def get_queryset(self):
        """Optimize queries with select_related."""
        if getattr(self, 'swagger_fake_view', False):
            return TestSection.objects.none()
        
        queryset = TestSection.objects.select_related('mock_test').order_by('order')
        
        # Filter by mock_test if provided
        mock_test_id = self.request.query_params.get('mock_test', None)
        if mock_test_id:
            queryset = queryset.filter(mock_test_id=mock_test_id)
        
        user = self.request.user
        
        # For STUDENT/GUEST, only show sections of published MockTests
        if user.role in ("STUDENT", "GUEST"):
            queryset = queryset.filter(mock_test__status=MockTest.Status.PUBLISHED)
        
        return queryset

    def perform_create(self, serializer):
        """Validate parent MockTest is editable before creating."""
        mock_test_id = serializer.validated_data.get('mock_test')
        if mock_test_id:
            try:
                validate_mock_test_editable(mock_test_id)
            except Exception as e:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"detail": str(e)})
        serializer.save()


class QuestionGroupViewSet(viewsets.ModelViewSet):
    """
    ViewSet for QuestionGroup model.
    
    Permissions check the parent MockTest's status before allowing modifications.
    """
    serializer_class = QuestionGroupSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = QuestionGroup.objects.all()

    def get_queryset(self):
        """Optimize queries with select_related."""
        if getattr(self, 'swagger_fake_view', False):
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
        
        # For STUDENT/GUEST, only show groups of published MockTests
        if user.role in ("STUDENT", "GUEST"):
            queryset = queryset.filter(section__mock_test__status=MockTest.Status.PUBLISHED)
        
        return queryset

    def perform_create(self, serializer):
        """Validate parent MockTest is editable before creating."""
        section = serializer.validated_data.get('section')
        if section:
            try:
                validate_mock_test_editable(section.mock_test)
            except Exception as e:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"detail": str(e)})
        serializer.save()


class QuestionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Question model.
    
    Permissions check the parent MockTest's status before allowing modifications.
    """
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = Question.objects.all()

    def get_queryset(self):
        """Optimize queries with select_related."""
        if getattr(self, 'swagger_fake_view', False):
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
        
        # For STUDENT/GUEST, only show questions of published MockTests
        if user.role in ("STUDENT", "GUEST"):
            queryset = queryset.filter(group__section__mock_test__status=MockTest.Status.PUBLISHED)
        
        return queryset

    def perform_create(self, serializer):
        """Validate parent MockTest is editable before creating."""
        group = serializer.validated_data.get('group')
        if group:
            try:
                validate_mock_test_editable(group.section.mock_test)
            except Exception as e:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"detail": str(e)})
        serializer.save()


class QuizViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Quiz model.
    """
    serializer_class = QuizSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = Quiz.objects.all()

    def get_queryset(self):
        """Filter queryset based on user role."""
        if getattr(self, 'swagger_fake_view', False):
            return Quiz.objects.none()
        
        user = self.request.user
        queryset = Quiz.objects.all().order_by('-created_at')
        
        # CENTER_ADMIN and TEACHER: See all Quizzes
        if user.role in ("CENTER_ADMIN", "TEACHER"):
            return queryset
        
        # STUDENT and GUEST: See only active Quizzes
        if user.role in ("STUDENT", "GUEST"):
            return queryset.filter(is_active=True)
        
        return Quiz.objects.none()

    def list(self, request, *args, **kwargs):
        """
        Optimized list endpoint to fix N+1 schema switching for 'created_by' field.
        """
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
        """Set created_by_id on create."""
        serializer.save(created_by_id=self.request.user.id)


class QuizQuestionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for QuizQuestion model.
    """
    serializer_class = QuizQuestionSerializer
    permission_classes = [IsAuthenticated, IsMockTestAdminOrTeacherOrReadOnly]
    queryset = QuizQuestion.objects.all()

    def get_queryset(self):
        """Optimize queries with select_related."""
        if getattr(self, 'swagger_fake_view', False):
            return QuizQuestion.objects.none()
        
        queryset = QuizQuestion.objects.select_related('quiz').order_by('order')
        
        # Filter by quiz if provided
        quiz_id = self.request.query_params.get('quiz', None)
        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)
        
        user = self.request.user
        
        # For STUDENT/GUEST, only show questions of active Quizzes
        if user.role in ("STUDENT", "GUEST"):
            queryset = queryset.filter(quiz__is_active=True)
        
        return queryset
