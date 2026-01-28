#apps/analytics/views.py
from django.apps import apps
from django.db.models import Avg, Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions

from apps.core.permissions import IsOwner, IsCenterAdmin, IsTeacher, IsStudent
from apps.core.tenant_utils import with_public_schema
from apps.analytics.serializers import (
    OwnerAnalyticsSerializer,
    CenterAdminAnalyticsSerializer,
    TeacherAnalyticsSerializer,
    StudentAnalyticsSerializer,
    RecentSubmissionSerializer,
    UpcomingDeadlineSerializer,
    RecentResultSerializer,
    SkillPerformanceSerializer,
)


class OwnerAnalyticsView(APIView):
    """
    Global analytics for platform owners.

    Runs in PUBLIC schema and aggregates:
    - total centers
    - total users
    - active centers
    - recent contact requests
    """

    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get(self, request, *args, **kwargs):
        Center = apps.get_model("centers", "Center")
        User = apps.get_model("authentication", "User")
        ContactRequest = apps.get_model("centers", "ContactRequest")

        def compute():
            total_centers = Center.objects.count()
            total_users = User.objects.count()
            active_centers_count = Center.objects.filter(
                is_active=True, deleted_at__isnull=True
            ).count()

            recent_qs = ContactRequest.objects.order_by("-created_at")[:10]
            recent_contact_requests = [
                {
                    "id": str(cr.id),
                    "center_name": cr.center_name,
                    "full_name": cr.full_name,
                    "phone_number": cr.phone_number,
                    "status": cr.status,
                    "created_at": cr.created_at,
                }
                for cr in recent_qs
            ]

            payload = {
                "total_centers": total_centers,
                "total_users": total_users,
                "active_centers_count": active_centers_count,
                "recent_contact_requests": recent_contact_requests,
            }
            return OwnerAnalyticsSerializer(payload).data

        data = with_public_schema(compute)
        return Response(data)


class CenterAdminAnalyticsView(APIView):
    """
    Tenant-level analytics for center admins.

    Runs in TENANT schema and aggregates:
    - total students / teachers
    - total groups
    - active exams (status=OPEN)
    """

    permission_classes = [permissions.IsAuthenticated, IsCenterAdmin]

    def get(self, request, *args, **kwargs):
        User = apps.get_model("authentication", "User")
        Group = apps.get_model("groups", "Group")
        ExamAssignment = apps.get_model("assignments", "ExamAssignment")
        center_id = request.user.center_id

        total_students = User.objects.filter(
            role=User.Role.STUDENT, 
            center=center_id
        ).count()
        total_teachers = User.objects.filter(
            role=User.Role.TEACHER, 
            center=center_id
        ).count()
        
        total_groups = Group.objects.count()
        active_exams_count = ExamAssignment.objects.filter(
            status=ExamAssignment.RoomStatus.OPEN
        ).count()

        payload = {
            "total_students": total_students,
            "total_teachers": total_teachers,
            "total_groups": total_groups,
            "active_exams_count": active_exams_count,
        }
        data = CenterAdminAnalyticsSerializer(payload).data
        return Response(data)


class TeacherAnalyticsView(APIView):
    """
    Tenant-level analytics for teachers.

    Aggregates:
    - number of groups they teach
    - total distinct students in their groups
    - submissions needing grading (status=SUBMITTED)
    - recent submissions with student names
    """

    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get(self, request, *args, **kwargs):
        user = request.user
        GroupMembership = apps.get_model("groups", "GroupMembership")
        Group = apps.get_model("groups", "Group")
        Submission = apps.get_model("attempts", "Submission")
        UserModel = apps.get_model("authentication", "User")

        # Groups where this user is a teacher
        my_group_ids = list(
        GroupMembership.objects.filter(
                user_id=user.id,
                role_in_group="TEACHER",
            ).values_list("group_id", flat=True)
        )
        my_groups_count = Group.objects.filter(id__in=my_group_ids).count()

        # Distinct students across those groups
        student_user_ids = list(
            GroupMembership.objects.filter(
                group_id__in=my_group_ids,
                role_in_group="STUDENT",
            )
            .values_list("user_id", flat=True)
            .distinct()
        )
        total_students = len(student_user_ids)

        # Submissions for assignments that target these groups
        ExamAssignment = apps.get_model("assignments", "ExamAssignment")
        HomeworkAssignment = apps.get_model("assignments", "HomeworkAssignment")

        exam_submissions_q = Submission.objects.filter(
            exam_assignment__assigned_groups__id__in=my_group_ids
        )
        hw_submissions_q = Submission.objects.filter(
            homework_assignment__assigned_groups__id__in=my_group_ids
        )
        submissions_q = (exam_submissions_q | hw_submissions_q).distinct()

        pending_grading_count = submissions_q.filter(
            status=Submission.Status.SUBMITTED
        ).count()

        recent_submissions_q = submissions_q.order_by("-created_at")[:10]

        # Batch fetch student names from public schema to avoid N+1
        from apps.core.tenant_utils import with_public_schema

        user_ids_set = {s.user_id for s in recent_submissions_q}

        def fetch_users():
            return {
                u.id: u
                for u in UserModel.objects.filter(id__in=user_ids_set)
            }

        user_map = with_public_schema(fetch_users)

        recent_submissions = []
        for sub in recent_submissions_q:
            u = user_map.get(sub.user_id)
            student_name = u.get_full_name() if u else str(sub.user_id)
            if sub.exam_assignment_id:
                assignment_title = sub.exam_assignment.title
            elif sub.homework_assignment_id:
                assignment_title = sub.homework_assignment.title
            else:
                assignment_title = "-"

            recent_submissions.append(
                RecentSubmissionSerializer(
                    {
                        "id": sub.id,
                        "student_name": student_name,
                        "assignment_title": assignment_title,
                        "score": float(sub.score) if sub.score is not None else None,
                        "submitted_at": sub.completed_at or sub.created_at,
                    }
                ).data
            )

        payload = {
            "my_groups_count": my_groups_count,
            "total_students": total_students,
            "pending_grading_count": pending_grading_count,
            "recent_submissions": recent_submissions,
        }
        data = TeacherAnalyticsSerializer(payload).data
        return Response(data)


class StudentAnalyticsView(APIView):
    """
    Tenant-level analytics for students.

    Aggregates:
    - average score across graded submissions
    - number of completed exams/homework
    - upcoming homework deadlines
    - recent graded results
    - lightweight skill performance summary
    """

    permission_classes = [permissions.IsAuthenticated, IsStudent]

    def get(self, request, *args, **kwargs):
        user = request.user
        Submission = apps.get_model("attempts", "Submission")
        HomeworkAssignment = apps.get_model("assignments", "HomeworkAssignment")
        GroupMembership = apps.get_model("groups", "GroupMembership")

        now = timezone.now()

        # Graded submissions (exams + homework)
        graded_qs = Submission.objects.filter(
            user_id=user.id,
            status=Submission.Status.GRADED,
        )

        completed_exams_count = graded_qs.count()
        avg_score_data = graded_qs.aggregate(avg=Avg("score"))
        avg_score_val = avg_score_data["avg"]
        average_score = float(avg_score_val) if avg_score_val is not None else 0.0

        # Upcoming homework deadlines where user has not yet submitted
        my_group_ids = list(
            GroupMembership.objects.filter(
                user_id=user.id,
                role_in_group="STUDENT",
            ).values_list("group_id", flat=True)
        )

        homework_qs = HomeworkAssignment.objects.filter(deadline__gt=now)
        homework_qs = homework_qs.filter(
            Q(assigned_groups__id__in=my_group_ids)
            | Q(assigned_user_ids__contains=[user.id])
        ).distinct()

        submitted_hw_ids = Submission.objects.filter(
            user_id=user.id,
            homework_assignment__isnull=False,
        ).values_list("homework_assignment_id", flat=True)

        homework_qs = homework_qs.exclude(id__in=submitted_hw_ids)

        upcoming_deadlines = [
            UpcomingDeadlineSerializer(
                {
                    "id": hw.id,
                    "title": hw.title,
                    "deadline": hw.deadline,
                    "type": "Homework",
                }
            ).data
            for hw in homework_qs.order_by("deadline")[:10]
        ]

        # Recent graded results
        recent_results_qs = graded_qs.order_by("-completed_at")[:10]
        recent_results = []
        for sub in recent_results_qs:
            if sub.exam_assignment_id:
                assignment_title = sub.exam_assignment.title
            elif sub.homework_assignment_id:
                assignment_title = sub.homework_assignment.title
            else:
                assignment_title = "-"

            recent_results.append(
                RecentResultSerializer(
                    {
                        "id": sub.id,
                        "assignment_title": assignment_title,
                        "score": float(sub.score) if sub.score is not None else None,
                        "status": sub.status,
                        "completed_at": sub.completed_at,
                    }
                ).data
            )

        # Skill performance (placeholder: overall score as a single skill)
        skill_performance = []
        if graded_qs.exists():
            skill_performance.append(
                SkillPerformanceSerializer(
                    {
                        "skill_name": "Overall",
                        "average_score": average_score,
                    }
                ).data
            )

        payload = {
            "average_score": average_score,
            "completed_exams_count": completed_exams_count,
            "upcoming_deadlines": upcoming_deadlines,
            "recent_results": recent_results,
            "skill_performance": skill_performance,
        }
        data = StudentAnalyticsSerializer(payload).data
        return Response(data)

