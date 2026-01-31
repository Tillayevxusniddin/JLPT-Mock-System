# apps/attempts/views.py
"""
Thin ViewSet for Submissions. JLPT grading, snapshot, security, and OpenAPI
schemas are documented in apps/attempts/swagger.py and services.py.
"""

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError, PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from .models import Submission
from .serializers import (
    SubmissionSerializer,
    SubmissionResultSerializer,
    SubmissionAnswerSerializer,
)
from .permissions import IsSubmissionOwnerOrTeacher, CanStartExam
from .services import StartExamService, StartHomeworkService, GradingService
from .swagger import submission_viewset_schema
from apps.assignments.models import ExamAssignment, HomeworkAssignment


@submission_viewset_schema
class SubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = SubmissionSerializer
    permission_classes = [IsAuthenticated, IsSubmissionOwnerOrTeacher]
    queryset = Submission.objects.all()

    def get_queryset(self):
        """Filter queryset based on user role."""
        if getattr(self, 'swagger_fake_view', False):
            return Submission.objects.none()
        
        user = self.request.user
        queryset = Submission.objects.select_related(
            'exam_assignment', 'homework_assignment'
        ).prefetch_related(
            'exam_assignment__assigned_groups',
            'homework_assignment__assigned_groups'
        ).order_by('-created_at')
        
        # CENTER_ADMIN: See all submissions
        if user.role == "CENTER_ADMIN":
            return queryset
        
        # TEACHER: See submissions for their groups
        if user.role == "TEACHER":
            from apps.groups.models import GroupMembership
            
            teaching_group_ids = GroupMembership.objects.filter(
                user_id=user.id,
                role_in_group="TEACHER"
            ).values_list('group_id', flat=True)
            
            if teaching_group_ids:
                return queryset.filter(
                    Q(exam_assignment__assigned_groups__id__in=teaching_group_ids) |
                    Q(homework_assignment__assigned_groups__id__in=teaching_group_ids)
                ).distinct()
            else:
                return Submission.objects.none()
        
        # STUDENT/GUEST: See only their own submissions
        if user.role in ("STUDENT", "GUEST"):
            return queryset.filter(user_id=user.id)
        
        return Submission.objects.none()

    def get_serializer_class(self):
        if self.action == "my_results":
            return SubmissionResultSerializer
        return SubmissionSerializer

    def perform_update(self, serializer):
        if serializer.instance.status == Submission.Status.GRADED:
            raise DRFValidationError(
                {"detail": "Cannot modify a graded submission. Results are immutable."}
            )
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status == Submission.Status.GRADED:
            raise DRFValidationError(
                {"detail": "Cannot delete a graded submission. Results are immutable."}
            )
        instance.delete()

    @action(detail=False, methods=["post"], url_path="start-exam", permission_classes=[IsAuthenticated, CanStartExam])
    def start_exam(self, request):
        user = request.user
        
        # Only students can start exams
        if user.role not in ("STUDENT", "GUEST"):
            raise PermissionDenied("Only students can start exams.")
        
        exam_assignment_id = request.data.get("exam_assignment_id")
        if not exam_assignment_id:
            raise DRFValidationError({"exam_assignment_id": "This field is required."})
        try:
            submission, exam_paper_data = StartExamService.start_exam(user, exam_assignment_id)
        except DjangoValidationError as e:
            raise DRFValidationError({"detail": str(e)})
        
        return Response({
            "submission_id": str(submission.id),
            "started_at": submission.started_at,
            "exam_paper": exam_paper_data,
            "message": "Exam started successfully. Timer begins now."
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="submit-exam")
    def submit_exam(self, request):
        user = request.user
        
        # Only students can submit exams
        if user.role not in ("STUDENT", "GUEST"):
            raise PermissionDenied("Only students can submit exams.")
        
        submission_id = request.data.get("submission_id")
        if not submission_id:
            raise DRFValidationError({"submission_id": "This field is required."})
        try:
            submission = Submission.objects.select_related(
                "exam_assignment", "homework_assignment",
            ).get(id=submission_id, user_id=user.id)
        except Submission.DoesNotExist:
            raise DRFValidationError({"submission_id": "Submission not found."})
        if submission.user_id != user.id:
            raise PermissionDenied("You can only submit your own submissions.")
        if submission.status != Submission.Status.STARTED:
            raise DRFValidationError(
                {"detail": "Only STARTED submissions can be submitted. This attempt is already submitted or graded."}
            )
        answers_data = request.data.get("answers")
        if not answers_data:
            raise DRFValidationError({"answers": "This field is required."})
        answer_serializer = SubmissionAnswerSerializer(data=answers_data)
        if not answer_serializer.is_valid():
            raise DRFValidationError({"answers": answer_serializer.errors})
        student_answers = answer_serializer.validated_data
        try:
            GradingService.grade_submission(submission, student_answers)
        except DjangoValidationError as e:
            raise DRFValidationError({"detail": str(e)})
        return Response({
            "submission_id": str(submission.id),
            "status": submission.status,
            "message": "Submission received. Your result is under review.",
            "note": "Results will be visible after the teacher publishes them.",
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="my-results")
    def my_results(self, request):
        user = request.user
        
        # Only students can view their own results
        if user.role not in ("STUDENT", "GUEST"):
            raise PermissionDenied("Only students can view their own results.")
        
        exam_assignment_id = request.query_params.get("exam_assignment_id")
        if not exam_assignment_id:
            raise DRFValidationError({"exam_assignment_id": "This query parameter is required."})
        try:
            exam_assignment = ExamAssignment.objects.get(id=exam_assignment_id)
        except ExamAssignment.DoesNotExist:
            raise DRFValidationError({"exam_assignment_id": "Exam assignment not found."})
        
        # Check if results are published
        if not exam_assignment.is_published:
            return Response({
                "message": "Results are not yet published. Please wait for the teacher to publish them.",
                "is_published": False
            }, status=status.HTTP_200_OK)
        
        # Get submission
        try:
            submission = Submission.objects.select_related(
                'exam_assignment', 'homework_assignment'
            ).get(
                user_id=user.id,
                exam_assignment=exam_assignment,
                status=Submission.Status.GRADED
            )
        except Submission.DoesNotExist:
            return Response({
                "message": "No graded submission found for this exam.",
                "is_published": True
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Serialize and return results
        serializer = SubmissionResultSerializer(submission, context={'request': request})
        return Response({
            "submission": serializer.data,
            "is_published": True
        }, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        exam_assignment_id = request.query_params.get("exam_assignment_id")
        homework_assignment_id = request.query_params.get("homework_assignment_id")
        if exam_assignment_id:
            queryset = queryset.filter(exam_assignment_id=exam_assignment_id)
        if homework_assignment_id:
            queryset = queryset.filter(homework_assignment_id=homework_assignment_id)
        page = self.paginate_queryset(queryset)
        items = page if page is not None else list(queryset)
        user_ids = {s.user_id for s in items if s.user_id}
        user_map = {}
        if user_ids:
            from apps.core.tenant_utils import with_public_schema
            from apps.authentication.models import User
            user_map = with_public_schema(
                lambda: {u.id: u for u in User.objects.filter(id__in=user_ids)}
            )
        serializer = self.get_serializer(
            items, many=True, context={"request": request, "user_map": user_map}
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="homework-start")
    def start_homework_item(self, request):
        user = request.user
        
        # Only students can start homework
        if user.role not in ("STUDENT", "GUEST"):
            raise PermissionDenied("Only students can start homework.")
        
        homework_assignment_id = request.data.get('homework_assignment_id')
        item_type = request.data.get('item_type')
        item_id = request.data.get('item_id')
        
        if not homework_assignment_id:
            raise DRFValidationError({"homework_assignment_id": "This field is required."})
        if not item_type:
            raise DRFValidationError({"item_type": "This field is required."})
        if not item_id:
            raise DRFValidationError({"item_id": "This field is required."})
        if item_type not in ("mock_test", "quiz"):
            raise DRFValidationError({"item_type": "Must be 'mock_test' or 'quiz'."})
        try:
            submission, item_data = StartHomeworkService.start_homework_item(
                user, homework_assignment_id, item_type, item_id,
            )
        except DjangoValidationError as e:
            raise DRFValidationError({"detail": str(e)})
        
        return Response({
            "submission_id": str(submission.id),
            "started_at": submission.started_at,
            "item_data": item_data,
            "item_type": item_type,
            "message": "Homework item started successfully."
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="show-result")
    def show_result(self, request):
        user = request.user
        
        # GUESTS are FORBIDDEN from practice mode
        if user.role == "GUEST":
            raise PermissionDenied(
                "Guests cannot use practice mode. Please submit your final answer."
            )
        
        # Only students can use practice mode
        if user.role != "STUDENT":
            raise PermissionDenied("Only students can use practice mode.")
        
        submission_id = request.data.get("submission_id")
        if not submission_id:
            raise DRFValidationError({"submission_id": "This field is required."})
        try:
            submission = Submission.objects.select_related(
                "homework_assignment", "mock_test", "quiz",
            ).get(id=submission_id, user_id=user.id)
        except Submission.DoesNotExist:
            raise DRFValidationError({"submission_id": "Submission not found."})
        if not submission.homework_assignment:
            raise DRFValidationError({"detail": "Practice mode is only available for homework submissions."})
        if submission.status == Submission.Status.GRADED:
            raise DRFValidationError({"detail": "This submission is already locked. You cannot use practice mode."})
        if submission.homework_assignment.deadline <= timezone.now():
            raise DRFValidationError({"detail": "Homework deadline has passed."})
        answers_data = request.data.get("answers")
        if not answers_data:
            raise DRFValidationError({"answers": "This field is required."})
        answer_serializer = SubmissionAnswerSerializer(data=answers_data)
        if not answer_serializer.is_valid():
            raise DRFValidationError({"answers": answer_serializer.errors})
        student_answers = answer_serializer.validated_data
        try:
            results = GradingService.calculate_result_dry_run(submission, student_answers)
        except DjangoValidationError as e:
            raise DRFValidationError({"detail": str(e)})
        
        return Response({
            "submission_id": str(submission.id),
            "status": submission.status,
            "results": results,
            "message": "Practice results. You can retry before submitting.",
            "note": "This is practice mode. Your submission is not locked."
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="submit-homework")
    def submit_homework(self, request):
        user = request.user
        
        # Only students/guests can submit homework
        if user.role not in ("STUDENT", "GUEST"):
            raise PermissionDenied("Only students can submit homework.")
        
        submission_id = request.data.get("submission_id")
        if not submission_id:
            raise DRFValidationError({"submission_id": "This field is required."})
        try:
            submission = Submission.objects.select_related(
                "homework_assignment", "mock_test", "quiz",
            ).get(id=submission_id, user_id=user.id)
        except Submission.DoesNotExist:
            raise DRFValidationError({"submission_id": "Submission not found."})
        if not submission.homework_assignment:
            raise DRFValidationError({"detail": "This endpoint is only for homework submissions."})
        if submission.status != Submission.Status.STARTED:
            raise DRFValidationError(
                {"detail": "Only STARTED submissions can be submitted. This attempt is already submitted or graded."}
            )
        if submission.homework_assignment.deadline <= timezone.now():
            raise DRFValidationError({"detail": "Homework deadline has passed."})
        answers_data = request.data.get("answers")
        if not answers_data:
            raise DRFValidationError({"answers": "This field is required."})
        answer_serializer = SubmissionAnswerSerializer(data=answers_data)
        if not answer_serializer.is_valid():
            raise DRFValidationError({"answers": answer_serializer.errors})
        student_answers = answer_serializer.validated_data
        try:
            results = GradingService.grade_submission(submission, student_answers)
        except DjangoValidationError as e:
            raise DRFValidationError({"detail": str(e)})
        
        # Check if results should be shown immediately
        show_results = submission.homework_assignment.show_results_immediately
        
        response_data = {
            "submission_id": str(submission.id),
            "status": submission.status,
            "message": "Homework submitted successfully. Your submission is now locked.",
        }
        
        if show_results:
            response_data["results"] = results
            response_data["note"] = "Results are shown immediately as configured."
        else:
            response_data["note"] = "Results will be available after review."
        
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="my-homework-results")
    def my_homework_results(self, request):
        user = request.user
        
        # Only students can view their own results
        if user.role not in ("STUDENT", "GUEST"):
            raise PermissionDenied("Only students can view their own results.")
        
        homework_assignment_id = request.query_params.get("homework_assignment_id")
        if not homework_assignment_id:
            raise DRFValidationError({"homework_assignment_id": "This query parameter is required."})
        try:
            homework = HomeworkAssignment.objects.prefetch_related(
                "mock_tests", "quizzes",
            ).get(id=homework_assignment_id)
        except HomeworkAssignment.DoesNotExist:
            raise DRFValidationError({"homework_assignment_id": "Homework assignment not found."})
        
        # Get all submissions for this homework
        submissions = Submission.objects.filter(
            user_id=user.id,
            homework_assignment=homework,
            status=Submission.Status.GRADED
        ).select_related('mock_test', 'quiz')
        
        results = []
        for submission in submissions:
            time_taken_seconds = None
            if submission.started_at and submission.completed_at:
                time_taken_seconds = max(0, int((submission.completed_at - submission.started_at).total_seconds()))
            item_data = {
                "submission_id": str(submission.id),
                "item_type": submission.resource_type,
                "item_id": str(submission.mock_test.id if submission.mock_test else submission.quiz.id),
                "item_title": submission.mock_test.title if submission.mock_test else submission.quiz.title,
                "status": submission.status,
                "score": float(submission.score) if submission.score else None,
                "started_at": submission.started_at,
                "completed_at": submission.completed_at,
                "time_taken_seconds": time_taken_seconds,
            }
            if homework.show_results_immediately:
                item_data["results"] = submission.results
            results.append(item_data)
        
        return Response({
            "homework_id": str(homework.id),
            "homework_title": homework.title,
            "show_results_immediately": homework.show_results_immediately,
            "submissions": results
        }, status=status.HTTP_200_OK)
