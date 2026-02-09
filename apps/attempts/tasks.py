# apps/attempts/tasks.py
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Submission
from .services import GradingService


GRACE_PERIOD_MINUTES = 10


def _get_duration_minutes(submission: Submission):
	if submission.exam_assignment and submission.exam_assignment.mock_test:
		return sum(s.duration for s in submission.exam_assignment.mock_test.sections.all())
	if submission.mock_test:
		return sum(s.duration for s in submission.mock_test.sections.all())
	if submission.quiz:
		return sum(q.duration for q in submission.quiz.questions.all())
	return None


@shared_task
def auto_submit_stuck_submissions():
	"""
	Auto-submit submissions stuck in STARTED beyond duration + grace period.
	Runs periodically (scheduled in Celery Beat).
	"""
	now = timezone.now()
	submissions = Submission.objects.select_related(
		"exam_assignment__mock_test",
		"homework_assignment",
		"mock_test",
		"quiz",
	).prefetch_related(
		"exam_assignment__mock_test__sections",
		"mock_test__sections",
		"quiz__questions",
	).filter(
		status=Submission.Status.STARTED,
		started_at__isnull=False,
	)

	for submission in submissions:
		duration_minutes = _get_duration_minutes(submission)
		if not duration_minutes:
			continue
		cutoff = submission.started_at + timedelta(
			minutes=duration_minutes + GRACE_PERIOD_MINUTES
		)
		if cutoff <= now:
			try:
				GradingService.grade_submission(submission, {})
			except Exception:
				continue