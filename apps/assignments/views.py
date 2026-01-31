# apps/assignments/views.py
"""
Thin ViewSets for ExamAssignment and HomeworkAssignment. Visibility rules,
N+1 handling, and OpenAPI schemas live in apps/assignments/swagger.py.
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q
from .models import ExamAssignment, HomeworkAssignment
from .serializers import (
    ExamAssignmentSerializer,
    HomeworkAssignmentSerializer,
    HomeworkDetailSerializer,
)
from .permissions import IsAssignmentManagerOrReadOnly
from .swagger import exam_assignment_viewset_schema, homework_assignment_viewset_schema
from apps.groups.models import GroupMembership


@exam_assignment_viewset_schema
class ExamAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = ExamAssignmentSerializer
    permission_classes = [IsAuthenticated, IsAssignmentManagerOrReadOnly]
    queryset = ExamAssignment.objects.all()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ExamAssignment.objects.none()
        user = self.request.user
        queryset = ExamAssignment.objects.select_related("mock_test").prefetch_related(
            "assigned_groups"
        ).order_by("-created_at")
        if user.role == "CENTER_ADMIN":
            return queryset
        if user.role == "TEACHER":
            teaching_group_ids = GroupMembership.objects.filter(
                user_id=user.id, role_in_group="TEACHER"
            ).values_list("group_id", flat=True)
            if teaching_group_ids:
                return queryset.filter(assigned_groups__id__in=teaching_group_ids).distinct()
            return ExamAssignment.objects.none()
        if user.role == "STUDENT":
            student_group_ids = GroupMembership.objects.filter(
                user_id=user.id, role_in_group="STUDENT"
            ).values_list("group_id", flat=True)
            if student_group_ids:
                return queryset.filter(assigned_groups__id__in=student_group_ids).distinct()
            return ExamAssignment.objects.none()
        return ExamAssignment.objects.none()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        assignments = page if page is not None else queryset
        user_ids = {a.created_by_id for a in assignments if a.created_by_id}
        user_map = {}
        if user_ids:
            from apps.core.tenant_utils import with_public_schema
            from apps.authentication.models import User
            user_map = with_public_schema(lambda: {u.id: u for u in User.objects.filter(id__in=user_ids)})
        serializer = self.get_serializer(
            assignments, many=True, context={"request": request, "user_map": user_map}
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(created_by_id=self.request.user.id)


@homework_assignment_viewset_schema
class HomeworkAssignmentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAssignmentManagerOrReadOnly]
    queryset = HomeworkAssignment.objects.all()

    def get_serializer_class(self):
        if self.action == "retrieve":
            return HomeworkDetailSerializer
        return HomeworkAssignmentSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return HomeworkAssignment.objects.none()
        user = self.request.user
        queryset = HomeworkAssignment.objects.prefetch_related(
            "assigned_groups", "mock_tests", "quizzes"
        ).order_by("-deadline")
        if user.role == "CENTER_ADMIN":
            return queryset
        if user.role == "TEACHER":
            teaching_group_ids = GroupMembership.objects.filter(
                user_id=user.id, role_in_group="TEACHER"
            ).values_list("group_id", flat=True)
            if teaching_group_ids:
                return queryset.filter(assigned_groups__id__in=teaching_group_ids).distinct()
            return HomeworkAssignment.objects.none()
        if user.role == "STUDENT":
            student_group_ids = GroupMembership.objects.filter(
                user_id=user.id, role_in_group="STUDENT"
            ).values_list("group_id", flat=True)
            query = Q(assigned_user_ids__contains=[user.id])
            if student_group_ids:
                query |= Q(assigned_groups__id__in=student_group_ids)
            return queryset.filter(query).distinct()
        if user.role == "GUEST":
            return queryset.filter(assigned_user_ids__contains=[user.id])
        return HomeworkAssignment.objects.none()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        assignments = page if page is not None else queryset
        user_ids = {a.created_by_id for a in assignments if a.created_by_id}
        user_map = {}
        if user_ids:
            from apps.core.tenant_utils import with_public_schema
            from apps.authentication.models import User
            user_map = with_public_schema(lambda: {u.id: u for u in User.objects.filter(id__in=user_ids)})
        serializer = self.get_serializer(
            assignments, many=True, context={"request": request, "user_map": user_map}
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(created_by_id=self.request.user.id)
