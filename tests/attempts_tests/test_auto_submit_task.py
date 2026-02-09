import pytest
from datetime import timedelta
from django.utils import timezone

from apps.attempts.models import Submission
from apps.attempts.tasks import auto_submit_stuck_submissions


@pytest.mark.django_db(transaction=True)
def test_grace_period_not_expired(student_user, exam_assignment_open, mock_test_n4):
    total_duration = sum(s.duration for s in mock_test_n4["mock_test"].sections.all())
    started_at = timezone.now() - timedelta(minutes=total_duration + 5)
    submission = Submission.objects.create(
        user_id=student_user.id,
        exam_assignment=exam_assignment_open,
        status=Submission.Status.STARTED,
        started_at=started_at,
    )

    auto_submit_stuck_submissions()
    submission.refresh_from_db()

    assert submission.status == Submission.Status.STARTED


@pytest.mark.django_db(transaction=True)
def test_auto_submit_after_grace_period(student_user, exam_assignment_open, mock_test_n4):
    total_duration = sum(s.duration for s in mock_test_n4["mock_test"].sections.all())
    started_at = timezone.now() - timedelta(minutes=total_duration + 25)
    submission = Submission.objects.create(
        user_id=student_user.id,
        exam_assignment=exam_assignment_open,
        status=Submission.Status.STARTED,
        started_at=started_at,
    )

    auto_submit_stuck_submissions()
    submission.refresh_from_db()

    assert submission.status == Submission.Status.GRADED
    assert float(submission.score) == 0.0
    assert submission.snapshot is not None
