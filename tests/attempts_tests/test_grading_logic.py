import pytest
from decimal import Decimal

from apps.attempts.services import GradingService
from apps.attempts.models import Submission
from apps.mock_tests.models import TestSection


@pytest.mark.django_db
def test_n4_scoring_accuracy(mock_test_n4, student_user, exam_assignment_open):
    submission = Submission.objects.create(
        user_id=student_user.id,
        exam_assignment=exam_assignment_open,
        status=Submission.Status.STARTED,
    )

    vocab_qs = mock_test_n4["questions"]["vocab"]
    grammar_qs = mock_test_n4["questions"]["grammar_reading"]
    listening_qs = mock_test_n4["questions"]["listening"]

    answers = {
        str(vocab_qs[0].id): vocab_qs[0].correct_option_index,
        str(vocab_qs[1].id): vocab_qs[1].correct_option_index,
        str(grammar_qs[0].id): grammar_qs[0].correct_option_index,
        str(grammar_qs[1].id): grammar_qs[1].correct_option_index,
        str(listening_qs[0].id): listening_qs[0].correct_option_index,
    }

    results = GradingService.grade_submission(submission, answers)

    lang_reading_score = results["jlpt_result"]["section_results"]["language_reading_combined"]["score"]
    listening_score = results["jlpt_result"]["section_results"]["listening"]["score"]

    assert lang_reading_score == pytest.approx(60.0)
    assert listening_score == pytest.approx(10.0)
    assert submission.snapshot is not None


@pytest.mark.django_db
def test_sectional_fail_with_high_total(mock_test_n4, student_user, exam_assignment_open):
    submission = Submission.objects.create(
        user_id=student_user.id,
        exam_assignment=exam_assignment_open,
        status=Submission.Status.STARTED,
    )

    vocab_qs = mock_test_n4["questions"]["vocab"]
    grammar_qs = mock_test_n4["questions"]["grammar_reading"]
    listening_qs = mock_test_n4["questions"]["listening"]

    answers = {str(q.id): q.correct_option_index for q in (vocab_qs + grammar_qs)}
    answers[str(listening_qs[0].id)] = listening_qs[0].correct_option_index

    results = GradingService.grade_submission(submission, answers)

    assert results["jlpt_result"]["total_passed"] is True
    assert results["jlpt_result"]["passed"] is False


@pytest.mark.django_db
def test_decimal_precision_in_jlpt_result(mock_test_n4):
    vocab_section = mock_test_n4["sections"]["vocab"]
    grammar_section = mock_test_n4["sections"]["grammar_reading"]
    listening_section = mock_test_n4["sections"]["listening"]

    section_scores = {
        "vocab": {"section": vocab_section, "score": Decimal("40.0")},
        "grammar": {"section": grammar_section, "score": Decimal("31.0")},
        "listening": {"section": listening_section, "score": Decimal("24.5")},
    }

    result = GradingService._calculate_jlpt_result(
        "N2",
        Decimal("95.5"),
        section_scores,
    )

    assert result["total_score"] == 95.5
    assert result["section_results"]["listening"]["score"] == 24.5
    assert result["section_results"]["language_knowledge"]["score"] == 55.5
    assert result["section_results"]["reading"]["score"] == 15.5
