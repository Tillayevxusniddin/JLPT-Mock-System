# apps/analytics/services.py
"""
Analytics service layer.

Responsibilities:
- Centralize analytics computations (views remain thin)
- Apply caching (Redis / Django cache) per role and tenant
- Normalize response formats for chart-friendly frontend consumption
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from django.apps import apps
from django.core.cache import cache
from django.db.models import Avg, Q
from django.utils import timezone

from apps.core.tenant_utils import get_current_schema, with_public_schema
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

# Cache TTLs (seconds)
OWNER_TTL = 60
CENTER_ADMIN_TTL = 60
TEACHER_TTL = 60
STUDENT_TTL = 60


def _cache_key(prefix: str, *parts: Any) -> str:
	suffix = ":".join(str(p) for p in parts if p is not None)
	return f"analytics:{prefix}:{suffix}" if suffix else f"analytics:{prefix}"


def _cache_get_or_set(key: str, ttl: int, compute_fn):
	cached = cache.get(key)
	if cached is not None:
		return cached
	data = compute_fn()
	cache.set(key, data, ttl)
	return data


def _build_skill_performance_from_results(graded_submissions) -> List[Dict[str, Any]]:
	"""
	Build skill_performance from Submission.results (JSONField).
	Returns list of {skill_name, average_score} in consistent order.
	"""
	section_scores: Dict[str, List[float]] = defaultdict(list)
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
				try:
					section_scores["quiz"].append(float(total) / float(max_s) * 100.0)
				except (TypeError, ValueError, ZeroDivisionError):
					pass

	out: List[Dict[str, Any]] = []
	for skill_key in SKILL_DISPLAY_ORDER:
		scores = section_scores.get(skill_key)
		display_name = SKILL_DISPLAY_NAMES.get(
			skill_key, skill_key.replace("_", " ").title()
		)
		if scores:
			avg = round(sum(scores) / len(scores), 2)
		else:
			avg = 0.0
		out.append({
			"skill_name": display_name,
			"average_score": avg,
		})

	# Include any extra sections found in results (stable ordering after defaults)
	for skill_key, scores in section_scores.items():
		if skill_key in SKILL_DISPLAY_ORDER:
			continue
		if scores:
			out.append({
				"skill_name": skill_key.replace("_", " ").title(),
				"average_score": round(sum(scores) / len(scores), 2),
			})
	return [SkillPerformanceSerializer(item).data for item in out]


def get_owner_analytics() -> Dict[str, Any]:
	"""Owner dashboard. Public schema only."""
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

	key = _cache_key("owner", "v1")
	return _cache_get_or_set(key, OWNER_TTL, lambda: with_public_schema(compute))


def get_center_admin_analytics(user) -> Dict[str, Any]:
	"""Center Admin dashboard. Tenant + public counts."""
	schema_name = get_current_schema()
	center_id = user.center_id

	def compute():
		User = apps.get_model("authentication", "User")
		Group = apps.get_model("groups", "Group")
		ExamAssignment = apps.get_model("assignments", "ExamAssignment")

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
		return CenterAdminAnalyticsSerializer(payload).data

	key = _cache_key("center_admin", schema_name)
	return _cache_get_or_set(key, CENTER_ADMIN_TTL, compute)


def get_teacher_analytics(user) -> Dict[str, Any]:
	"""Teacher dashboard. Tenant + public user_map for names."""
	schema_name = get_current_schema()

	def compute():
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
			return TeacherAnalyticsSerializer(payload).data

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
		return TeacherAnalyticsSerializer(payload).data

	key = _cache_key("teacher", schema_name, user.id)
	return _cache_get_or_set(key, TEACHER_TTL, compute)


def get_student_analytics(user) -> Dict[str, Any]:
	"""Student dashboard. Tenant-level."""
	schema_name = get_current_schema()

	def compute():
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
		payload = {
			"average_score": average_score,
			"completed_exams_count": completed_count,
			"upcoming_deadlines": upcoming_deadlines,
			"recent_results": recent_results,
			"skill_performance": skill_performance,
			"submission_trend_count": None,
		}
		return StudentAnalyticsSerializer(payload).data

	key = _cache_key("student", schema_name, user.id)
	return _cache_get_or_set(key, STUDENT_TTL, compute)