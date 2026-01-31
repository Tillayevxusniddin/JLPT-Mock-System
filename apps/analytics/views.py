# apps/analytics/views.py
"""
Role-based analytics dashboards. Owner: public schema only. Center Admin / Teacher / Student:
tenant + public (user counts via with_public_schema). Performance: Count/Avg, user_map, select_related.
Documented in apps/analytics/swagger.py.
"""
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
from apps.analytics.swagger import (
    owner_analytics_schema,
    center_admin_analytics_schema,
    teacher_analytics_schema,
    student_analytics_schema,
)

# JLPT section display order and display names for skill_performance
SKILL_DISPLAY_ORDER = (
    "language_knowledge",
    "reading",
    "listening",
    "language_reading_combined",
    "quiz",
)
SKILL_DISPLAY_NAMES = {
    "language_knowledge": "Vocabulary",
    "reading": "Reading",
    "listening": "Listening",
    "language_reading_combined": "Language & Reading",
    "quiz": "Quiz",
}


@owner_analytics_schema
class OwnerAnalyticsView(APIView):
    """Global analytics for platform owners. PUBLIC schema only: Center, User, ContactRequest."""
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get(self, request, *args, **kwargs):
        def compute():
            Center = apps.get_model("centers", "Center")
            User = apps.get_model("authentication", "User")
            ContactRequest = apps.get_model("centers", "ContactRequest")
            total_centers = Center.objects.count()
            total_users = User.objects.count()
            active_centers_count = Center.objects.filter(
                status=Center.Status.ACTIVE,
                schema_name__isnull=False,
            ).exclude(schema_name="").count()
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
                "growth_centers_pct": None,
            }
            return OwnerAnalyticsSerializer(payload).data

        data = with_public_schema(compute)
        return Response(data)


@center_admin_analytics_schema
class CenterAdminAnalyticsView(APIView):
    """Tenant-level analytics for center admins. User counts from PUBLIC; Group/Exam from tenant."""
    permission_classes = [permissions.IsAuthenticated, IsCenterAdmin]

    def get(self, request, *args, **kwargs):
        User = apps.get_model("authentication", "User")
        Group = apps.get_model("groups", "Group")
        ExamAssignment = apps.get_model("assignments", "ExamAssignment")
        center_id = request.user.center_id

        def public_counts():
            return {
                "total_students": User.objects.filter(
                    role=User.Role.STUDENT, center_id=center_id,
                ).count(),
                "total_teachers": User.objects.filter(
                    role=User.Role.TEACHER, center_id=center_id,
                ).count(),
            }

        counts = with_public_schema(public_counts)
        total_groups = Group.objects.count()
        active_exams_count = ExamAssignment.objects.filter(
            status=ExamAssignment.RoomStatus.OPEN,
        ).count()
        payload = {
            "total_students": counts["total_students"],
            "total_teachers": counts["total_teachers"],
            "total_groups": total_groups,
            "active_exams_count": active_exams_count,
            "growth_students_pct": None,
        }
        return Response(CenterAdminAnalyticsSerializer(payload).data)


@teacher_analytics_schema
class TeacherAnalyticsView(APIView):
    """Tenant + Public: distinct students in teacher's groups; pending (SUBMITTED); user_map for names."""
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get(self, request, *args, **kwargs):
        user = request.user
        GroupMembership = apps.get_model("groups", "GroupMembership")
        Group = apps.get_model("groups", "Group")
        Submission = apps.get_model("attempts", "Submission")
        UserModel = apps.get_model("authentication", "User")

        my_group_ids = list(
            GroupMembership.objects.filter(
                user_id=user.id,
                role_in_group="TEACHER",
            ).values_list("group_id", flat=True)
        )
        if not my_group_ids:
            payload = {
                "my_groups_count": 0,
                "total_students": 0,
                "pending_grading_count": 0,
                "recent_submissions": [],
                "submission_trend_count": None,
            }
            return Response(TeacherAnalyticsSerializer(payload).data)

        my_groups_count = Group.objects.filter(id__in=my_group_ids).count()
        student_user_ids = set(
            GroupMembership.objects.filter(
                group_id__in=my_group_ids,
                role_in_group="STUDENT",
            ).values_list("user_id", flat=True)
        )
        total_students = len(student_user_ids)

        exam_submissions_q = Submission.objects.filter(
            exam_assignment__assigned_groups__id__in=my_group_ids,
        )
        hw_submissions_q = Submission.objects.filter(
            homework_assignment__assigned_groups__id__in=my_group_ids,
        )
        submissions_q = (exam_submissions_q | hw_submissions_q).distinct()
        pending_grading_count = submissions_q.filter(
            status=Submission.Status.SUBMITTED,
        ).count()

        recent_submissions_q = (
            submissions_q.select_related("exam_assignment", "homework_assignment")
            .order_by("-created_at")[:10]
        )
        user_ids_set = {s.user_id for s in recent_submissions_q}
        user_map = (
            with_public_schema(
                lambda: {u.id: u for u in UserModel.objects.filter(id__in=user_ids_set)}
            )
            if user_ids_set
            else {}
        )

        def full_name(u):
            if not u:
                return ""
            return (
                (getattr(u, "get_full_name", None) and u.get_full_name())
                or getattr(u, "email", "")
                or str(u.id)
            )

        recent_submissions = []
        for sub in recent_submissions_q:
            u = user_map.get(sub.user_id)
            assignment_title = "-"
            if sub.exam_assignment_id and sub.exam_assignment:
                assignment_title = sub.exam_assignment.title
            elif sub.homework_assignment_id and sub.homework_assignment:
                assignment_title = sub.homework_assignment.title
            recent_submissions.append(
                RecentSubmissionSerializer(
                    {
                        "id": sub.id,
                        "student_name": full_name(u) or str(sub.user_id),
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
            "submission_trend_count": None,
        }
        return Response(TeacherAnalyticsSerializer(payload).data)


def _build_skill_performance_from_results(graded_submissions):
    """
    Build skill_performance from Submission.results (JSONField).
    JLPT: jlpt_result.section_results (language_knowledge, reading, listening or
    language_reading_combined, listening). Quiz: single "Quiz" from total_score/max_score.
    Returns list of {skill_name, average_score} in consistent order with display names.
    """
    from collections import defaultdict
    section_scores = defaultdict(list)
    for sub in graded_submissions:
        results = sub.results or {}
        if not isinstance(results, dict):
            continue
        jlpt = results.get("jlpt_result") or {}
        section_results = jlpt.get("section_results") or {}
        for skill_key, data in section_results.items():
            if isinstance(data, dict) and "score" in data:
                try:
                    section_scores[skill_key].append(float(data["score"]))
                except (TypeError, ValueError):
                    pass
        if not section_results and results.get("resource_type") == "quiz":
            total = results.get("total_score")
            max_s = results.get("max_score")
            if total is not None and max_s and max_s > 0:
                section_scores["quiz"].append(float(total) / float(max_s) * 100.0)
    out = []
    for skill_key in SKILL_DISPLAY_ORDER:
        scores = section_scores.get(skill_key)
        if not scores:
            continue
        display_name = SKILL_DISPLAY_NAMES.get(
            skill_key, skill_key.replace("_", " ").title()
        )
        out.append({
            "skill_name": display_name,
            "average_score": round(sum(scores) / len(scores), 2),
        })
    for skill_key, scores in section_scores.items():
        if skill_key in SKILL_DISPLAY_ORDER:
            continue
        if scores:
            out.append({
                "skill_name": skill_key.replace("_", " ").title(),
                "average_score": round(sum(scores) / len(scores), 2),
            })
    return [SkillPerformanceSerializer(item).data for item in out]


@student_analytics_schema
class StudentAnalyticsView(APIView):
    """Tenant-level student dashboard. Upcoming = assigned_groups OR assigned_user_ids, exclude GRADED."""
    permission_classes = [permissions.IsAuthenticated, IsStudent]

    def get(self, request, *args, **kwargs):
        user = request.user
        Submission = apps.get_model("attempts", "Submission")
        HomeworkAssignment = apps.get_model("assignments", "HomeworkAssignment")
        GroupMembership = apps.get_model("groups", "GroupMembership")
        now = timezone.now()

        graded_qs = Submission.objects.filter(
            user_id=user.id,
            status=Submission.Status.GRADED,
        ).select_related("exam_assignment", "homework_assignment")
        completed_count = graded_qs.count()
        avg_score_data = graded_qs.aggregate(avg=Avg("score"))
        avg_val = avg_score_data.get("avg")
        average_score = round(float(avg_val), 2) if avg_val is not None else 0.0

        my_group_ids = list(
            GroupMembership.objects.filter(
                user_id=user.id,
                role_in_group="STUDENT",
            ).values_list("group_id", flat=True)
        )
        homework_qs = (
            HomeworkAssignment.objects.filter(deadline__gt=now)
            .filter(
                Q(assigned_groups__id__in=my_group_ids)
                | Q(assigned_user_ids__contains=[user.id])
            )
            .distinct()
        )
        completed_hw_ids = set(
            graded_qs.filter(homework_assignment__isnull=False).values_list(
                "homework_assignment_id", flat=True
            )
        )
        homework_qs = homework_qs.exclude(id__in=completed_hw_ids)
        upcoming_deadlines = [
            UpcomingDeadlineSerializer({
                "id": hw.id,
                "title": hw.title,
                "deadline": hw.deadline,
                "type": "Homework",
            }).data
            for hw in homework_qs.order_by("deadline")[:10]
        ]

        recent_results_qs = graded_qs.order_by("-completed_at")[:10]
        recent_results = []
        for sub in recent_results_qs:
            title = "-"
            if sub.exam_assignment:
                title = sub.exam_assignment.title
            elif sub.homework_assignment:
                title = sub.homework_assignment.title
            recent_results.append(
                RecentResultSerializer({
                    "id": sub.id,
                    "assignment_title": title,
                    "score": float(sub.score) if sub.score is not None else None,
                    "status": sub.status,
                    "completed_at": sub.completed_at,
                }).data
            )

        skill_performance = _build_skill_performance_from_results(graded_qs)
        if not skill_performance and average_score >= 0:
            skill_performance = [
                SkillPerformanceSerializer({
                    "skill_name": "Overall",
                    "average_score": average_score,
                }).data
            ]

        payload = {
            "average_score": average_score,
            "completed_exams_count": completed_count,
            "upcoming_deadlines": upcoming_deadlines,
            "recent_results": recent_results,
            "skill_performance": skill_performance,
            "submission_trend_count": None,
        }
        return Response(StudentAnalyticsSerializer(payload).data)
