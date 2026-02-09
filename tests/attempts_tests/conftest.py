"""
Fixtures for Attempts app QA automation.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.centers.models import Center
from apps.groups.models import Group, GroupMembership
from apps.mock_tests.models import MockTest, TestSection, QuestionGroup, Question
from apps.assignments.models import ExamAssignment, HomeworkAssignment
from apps.attempts.models import Submission
from apps.attempts.services import GradingService

User = get_user_model()


@pytest.fixture(scope="session", autouse=True)
def disable_center_schema_creation_for_tests():
    """Disable Center signals during tests to avoid tenant migration side effects."""
    from django.db.models.signals import post_save
    from apps.centers.signals import (
        run_migrations_for_new_center,
        create_free_subscription_for_new_center,
    )
    post_save.disconnect(run_migrations_for_new_center, sender=Center)
    post_save.disconnect(create_free_subscription_for_new_center, sender=Center)


def _get_error_detail(response, key):
    """Return error detail for a field, supporting wrapped error responses."""
    data = response.data
    if isinstance(data, dict) and "error" in data and isinstance(data["error"], dict):
        data = data["error"]
    if isinstance(data, dict):
        return data.get(key)
    return None


@pytest.fixture(autouse=True)
def mock_cache(monkeypatch):
    """Mock django.core.cache to avoid external cache dependency."""
    from django.core import cache

    class _DummyCache:
        def get(self, *args, **kwargs):
            return None

        def set(self, *args, **kwargs):
            return True

        def delete(self, *args, **kwargs):
            return True

    monkeypatch.setattr(cache, "cache", _DummyCache())


@pytest.fixture(autouse=True)
def mock_celery_task(monkeypatch):
    """Mock Celery delay/apply_async for attempts tasks."""
    from apps.attempts import tasks

    monkeypatch.setattr(tasks.auto_submit_stuck_submissions, "delay", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(tasks.auto_submit_stuck_submissions, "apply_async", lambda *a, **k: None, raising=False)


@pytest.fixture
def api_client():
    client = APIClient()
    client.raise_request_exception = True
    return client


@pytest.fixture
def test_center(db):
    return Center.objects.create(name="Test Center", schema_name="public")


@pytest.fixture
def foreign_center(db):
    return Center.objects.create(name="Foreign Center", schema_name="foreign")


@pytest.fixture
def admin_user(db, test_center):
    return User.objects.create_user(
        email="admin@center.test",
        password="Pass12345!",
        role=User.Role.CENTERADMIN,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def teacher_user(db, test_center):
    return User.objects.create_user(
        email="teacher@center.test",
        password="Pass12345!",
        role=User.Role.TEACHER,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def student_user(db, test_center):
    return User.objects.create_user(
        email="student@center.test",
        password="Pass12345!",
        role=User.Role.STUDENT,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def foreign_student(db, foreign_center):
    return User.objects.create_user(
        email="student@foreign.test",
        password="Pass12345!",
        role=User.Role.STUDENT,
        center=foreign_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def group_a(db):
    return Group.objects.create(name="Group A")


@pytest.fixture
def membership_student_a(db, student_user, group_a):
    return GroupMembership.objects.create(
        group=group_a,
        user_id=student_user.id,
        role_in_group=GroupMembership.ROLE_STUDENT,
    )


@pytest.fixture
def mock_test_n4(db, admin_user):
    mock_test = MockTest.objects.create(
        title="N4 Full Mock",
        level=MockTest.Level.N4,
        status=MockTest.Status.PUBLISHED,
        created_by_id=admin_user.id,
    )

    vocab = TestSection.objects.create(
        mock_test=mock_test,
        name="Vocabulary",
        section_type=TestSection.SectionType.VOCAB,
        duration=20,
        order=1,
        total_score=60,
    )
    grammar_reading = TestSection.objects.create(
        mock_test=mock_test,
        name="Grammar & Reading",
        section_type=TestSection.SectionType.GRAMMAR_READING,
        duration=40,
        order=2,
        total_score=60,
    )
    listening = TestSection.objects.create(
        mock_test=mock_test,
        name="Listening",
        section_type=TestSection.SectionType.LISTENING,
        duration=30,
        order=3,
        total_score=60,
    )

    vocab_group = QuestionGroup.objects.create(section=vocab, mondai_number=1, title="Vocab")
    grammar_group = QuestionGroup.objects.create(section=grammar_reading, mondai_number=2, title="Grammar")
    listening_group = QuestionGroup.objects.create(section=listening, mondai_number=3, title="Listening")

    def _create_question(group, qn, score):
        return Question.objects.create(
            group=group,
            text=f"Question {qn}",
            question_number=qn,
            score=score,
            order=qn,
            options=[
                {"id": 1, "text": "A", "is_correct": False},
                {"id": 2, "text": "B", "is_correct": True},
                {"id": 3, "text": "C", "is_correct": False},
                {"id": 4, "text": "D", "is_correct": False},
            ],
        )

    vocab_questions = [
        _create_question(vocab_group, 1, 15),
        _create_question(vocab_group, 2, 15),
        _create_question(vocab_group, 3, 15),
        _create_question(vocab_group, 4, 15),
    ]
    grammar_questions = [
        _create_question(grammar_group, 5, 15),
        _create_question(grammar_group, 6, 15),
        _create_question(grammar_group, 7, 15),
    ]
    listening_questions = [
        _create_question(listening_group, 8, 10),
        _create_question(listening_group, 9, 10),
        _create_question(listening_group, 10, 10),
    ]

    return {
        "mock_test": mock_test,
        "sections": {
            "vocab": vocab,
            "grammar_reading": grammar_reading,
            "listening": listening,
        },
        "questions": {
            "vocab": vocab_questions,
            "grammar_reading": grammar_questions,
            "listening": listening_questions,
        },
    }


@pytest.fixture
def exam_assignment_open(db, teacher_user, group_a, mock_test_n4):
    exam = ExamAssignment.objects.create(
        title="N4 Exam",
        description="Exam",
        mock_test=mock_test_n4["mock_test"],
        status=ExamAssignment.RoomStatus.OPEN,
        created_by_id=teacher_user.id,
    )
    exam.assigned_groups.set([group_a.id])
    return exam


@pytest.fixture
def homework_assignment(db, teacher_user, group_a, mock_test_n4):
    hw = HomeworkAssignment.objects.create(
        title="N4 Homework",
        description="HW",
        deadline=timezone.now() + timedelta(days=7),
        created_by_id=teacher_user.id,
        show_results_immediately=True,
    )
    hw.assigned_groups.set([group_a.id])
    hw.mock_tests.set([mock_test_n4["mock_test"].id])
    return hw


@pytest.fixture
def started_submission(db, student_user, exam_assignment_open):
    return Submission.objects.create(
        user_id=student_user.id,
        exam_assignment=exam_assignment_open,
        status=Submission.Status.STARTED,
        started_at=timezone.now(),
    )


@pytest.fixture
def graded_submission(db, student_user, exam_assignment_open, mock_test_n4):
    submission = Submission.objects.create(
        user_id=student_user.id,
        exam_assignment=exam_assignment_open,
        status=Submission.Status.STARTED,
        started_at=timezone.now() - timedelta(minutes=30),
    )
    answers = {str(q.id): q.correct_option_index for q in (
        mock_test_n4["questions"]["vocab"] +
        mock_test_n4["questions"]["grammar_reading"] +
        mock_test_n4["questions"]["listening"]
    )}
    GradingService.grade_submission(submission, answers)
    submission.refresh_from_db()
    return submission


@pytest.fixture
def api_client_student(api_client, student_user):
    api_client.force_authenticate(user=student_user)
    return api_client


@pytest.fixture
def api_client_admin(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def api_client_foreign(api_client, foreign_student):
    api_client.force_authenticate(user=foreign_student)
    return api_client
