"""
Fixtures for Mock Tests app QA automation.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.centers.models import Center
from apps.mock_tests.models import MockTest, TestSection, QuestionGroup, Question, Quiz, QuizQuestion

User = get_user_model()


@pytest.fixture(scope="session", autouse=True)
def disable_center_schema_creation_for_tests():
    """
    Disable Center signals during tests to avoid tenant migration side effects.
    """
    from django.db.models.signals import post_save
    from apps.centers.signals import (
        run_migrations_for_new_center,
        create_free_subscription_for_new_center,
    )
    post_save.disconnect(run_migrations_for_new_center, sender=Center)
    post_save.disconnect(create_free_subscription_for_new_center, sender=Center)


def _get_error_detail(response):
    """
    Extract error details from DRF error responses.
    Matches the shared helper pattern used in other test modules.
    """
    if hasattr(response, "data"):
        data = response.data
        if isinstance(data, dict):
            if "detail" in data:
                return data["detail"]
            for value in data.values():
                if isinstance(value, list) and value:
                    return value[0]
                if isinstance(value, dict):
                    return _get_error_detail(type("obj", (), {"data": value})())
                return value
        if isinstance(data, list) and data:
            return data[0]
    return str(response.data) if hasattr(response, "data") else ""


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
def guest_user(db, test_center):
    return User.objects.create_user(
        email="guest@center.test",
        password="Pass12345!",
        role=User.Role.GUEST,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def foreign_teacher_user(db, foreign_center):
    return User.objects.create_user(
        email="teacher@foreign.test",
        password="Pass12345!",
        role=User.Role.TEACHER,
        center=foreign_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def api_client_admin(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def api_client_teacher(api_client, teacher_user):
    api_client.force_authenticate(user=teacher_user)
    return api_client


@pytest.fixture
def api_client_student(api_client, student_user):
    api_client.force_authenticate(user=student_user)
    return api_client


@pytest.fixture
def api_client_guest(api_client, guest_user):
    api_client.force_authenticate(user=guest_user)
    return api_client


@pytest.fixture
def options_payload():
    return [
        {"text": "A", "is_correct": False},
        {"text": "B", "is_correct": True},
        {"text": "C", "is_correct": False},
        {"text": "D", "is_correct": False},
    ]


@pytest.fixture
def draft_mock_test(db, admin_user):
    return MockTest.objects.create(
        title="JLPT N5 Draft",
        level=MockTest.Level.N5,
        description="Draft test",
        status=MockTest.Status.DRAFT,
        created_by_id=admin_user.id,
        pass_score=90,
        total_score=0,
    )


@pytest.fixture
def published_mock_test(db, admin_user):
    return MockTest.objects.create(
        title="JLPT N5 Published",
        level=MockTest.Level.N5,
        description="Published test",
        status=MockTest.Status.PUBLISHED,
        created_by_id=admin_user.id,
        pass_score=90,
        total_score=0,
    )


@pytest.fixture
def full_hierarchy(draft_mock_test, options_payload):
    section = TestSection.objects.create(
        mock_test=draft_mock_test,
        name="Vocabulary",
        section_type=TestSection.SectionType.VOCAB,
        duration=20,
        order=1,
        total_score=0,
    )
    group = QuestionGroup.objects.create(
        section=section,
        mondai_number=1,
        title="Kanji Reading",
        instruction="Choose the correct reading.",
        order=1,
    )
    question1 = Question.objects.create(
        group=group,
        text="Q1",
        question_number=1,
        score=2,
        order=1,
        options=options_payload,
        correct_option_index=1,
    )
    question2 = Question.objects.create(
        group=group,
        text="Q2",
        question_number=2,
        score=3,
        order=2,
        options=options_payload,
        correct_option_index=1,
    )
    return {
        "mock_test": draft_mock_test,
        "section": section,
        "group": group,
        "questions": [question1, question2],
    }


@pytest.fixture
def full_hierarchy_teacher(db, teacher_user, options_payload):
    mock_test = MockTest.objects.create(
        title="Teacher Draft",
        level=MockTest.Level.N5,
        description="Teacher-owned test",
        status=MockTest.Status.DRAFT,
        created_by_id=teacher_user.id,
        pass_score=90,
        total_score=0,
    )
    section = TestSection.objects.create(
        mock_test=mock_test,
        name="Vocabulary",
        section_type=TestSection.SectionType.VOCAB,
        duration=20,
        order=1,
        total_score=0,
    )
    group = QuestionGroup.objects.create(
        section=section,
        mondai_number=1,
        title="Kanji Reading",
        instruction="Choose the correct reading.",
        order=1,
    )
    question = Question.objects.create(
        group=group,
        text="Q1",
        question_number=1,
        score=2,
        order=1,
        options=options_payload,
        correct_option_index=1,
    )
    return {
        "mock_test": mock_test,
        "section": section,
        "group": group,
        "questions": [question],
    }


@pytest.fixture
def full_hierarchy_published(published_mock_test, options_payload):
    section = TestSection.objects.create(
        mock_test=published_mock_test,
        name="Vocabulary",
        section_type=TestSection.SectionType.VOCAB,
        duration=20,
        order=1,
        total_score=0,
    )
    group = QuestionGroup.objects.create(
        section=section,
        mondai_number=1,
        title="Kanji Reading",
        instruction="Choose the correct reading.",
        order=1,
    )
    question1 = Question.objects.create(
        group=group,
        text="Q1",
        question_number=1,
        score=2,
        order=1,
        options=options_payload,
        correct_option_index=1,
    )
    question2 = Question.objects.create(
        group=group,
        text="Q2",
        question_number=2,
        score=3,
        order=2,
        options=options_payload,
        correct_option_index=1,
    )
    return {
        "mock_test": published_mock_test,
        "section": section,
        "group": group,
        "questions": [question1, question2],
    }


@pytest.fixture
def quiz_with_question(db, admin_user, options_payload):
    quiz = Quiz.objects.create(
        title="Quick Quiz",
        description="Quiz",
        created_by_id=admin_user.id,
        is_active=True,
        default_question_duration=20,
    )
    question = QuizQuestion.objects.create(
        quiz=quiz,
        text="Quiz Q1",
        question_type=QuizQuestion.QuestionType.QUIZ,
        duration=20,
        points=1,
        order=1,
        options=options_payload,
        correct_option_index=1,
    )
    return {"quiz": quiz, "question": question}
