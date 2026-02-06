# apps/analytics/views.py
"""
Role-based analytics dashboards. Views are thin and delegate to services.
Documented in apps/analytics/swagger.py.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions

from apps.core.permissions import IsOwner, IsCenterAdmin, IsTeacher, IsStudent
from apps.analytics.services import (
    get_owner_analytics,
    get_center_admin_analytics,
    get_teacher_analytics,
    get_student_analytics,
)
from apps.analytics.swagger import (
    owner_analytics_schema,
    center_admin_analytics_schema,
    teacher_analytics_schema,
    student_analytics_schema,
)


@owner_analytics_schema
class OwnerAnalyticsView(APIView):
    """Global analytics for platform owners. PUBLIC schema only: Center, User, ContactRequest."""
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get(self, request, *args, **kwargs):
        return Response(get_owner_analytics())


@center_admin_analytics_schema
class CenterAdminAnalyticsView(APIView):
    """Tenant-level analytics for center admins. User counts from PUBLIC; Group/Exam from tenant."""
    permission_classes = [permissions.IsAuthenticated, IsCenterAdmin]

    def get(self, request, *args, **kwargs):
        return Response(get_center_admin_analytics(request.user))


@teacher_analytics_schema
class TeacherAnalyticsView(APIView):
    """Tenant + Public: distinct students in teacher's groups; pending (SUBMITTED); user_map for names."""
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get(self, request, *args, **kwargs):
        return Response(get_teacher_analytics(request.user))


@student_analytics_schema
class StudentAnalyticsView(APIView):
    """Tenant-level student dashboard. Upcoming = assigned_groups OR assigned_user_ids, exclude GRADED."""
    permission_classes = [permissions.IsAuthenticated, IsStudent]

    def get(self, request, *args, **kwargs):
        return Response(get_student_analytics(request.user))
