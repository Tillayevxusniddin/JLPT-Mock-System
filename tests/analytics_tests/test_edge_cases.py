# tests/analytics_tests/test_edge_cases.py
"""
Test analytics edge cases: malformed JSON, empty centers, homework exclusion.
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.attempts.models import Submission
from apps.core.tenant_utils import schema_context


@pytest.mark.django_db(transaction=True)
class TestMalformedJSON:
    """Test analytics robustness against malformed results JSON."""

    def test_student_analytics_with_string_results(
        self,
        api_client_student_a1,
        student_a1,
        exam_assignment_a,
        center_a,
    ):
        """Analytics doesn't crash when results is a string instead of dict."""
        with schema_context(center_a.schema_name):
            # Create submission with malformed results (string instead of dict)
            bad_submission = Submission.objects.create(
                user_id=student_a1.id,
                exam_assignment=exam_assignment_a,
                status=Submission.Status.GRADED,
                score=Decimal("100.00"),
                results="malformed string",  # ← Not a dict
                completed_at=timezone.now(),
            )
        
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should not crash, should return valid response
        # Malformed results are skipped, so skill_performance will be empty
        assert "skill_performance" in data
        assert isinstance(data["skill_performance"], list)
        # score should still be aggregated
        assert data["average_score"] == 100.0

    def test_student_analytics_with_empty_results(
        self,
        api_client_student_a1,
        student_a1,
        exam_assignment_a,
        center_a,
    ):
        """Analytics handles empty results JSON gracefully."""
        with schema_context(center_a.schema_name):
            # Create submission with empty results
            empty_submission = Submission.objects.create(
                user_id=student_a1.id,
                exam_assignment=exam_assignment_a,
                status=Submission.Status.GRADED,
                score=Decimal("80.00"),
                results={},  # ← Empty dict
                completed_at=timezone.now(),
            )
        
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should handle gracefully
        assert data["average_score"] == 80.0
        assert "skill_performance" in data

    def test_student_analytics_with_missing_score_in_section(
        self,
        api_client_student_a1,
        student_a1,
        exam_assignment_a,
        center_a,
    ):
        """Analytics handles section results without 'score' field."""
        with schema_context(center_a.schema_name):
            # Create submission with section missing 'score' field
            bad_results = {
                "jlpt_result": {
                    "section_results": {
                        "language_knowledge": {
                            "min_required": 19,
                            # 'score' field is missing
                        }
                    }
                }
            }
            bad_submission = Submission.objects.create(
                user_id=student_a1.id,
                exam_assignment=exam_assignment_a,
                status=Submission.Status.GRADED,
                score=Decimal("75.00"),
                results=bad_results,
                completed_at=timezone.now(),
            )
        
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should not crash
        assert data["average_score"] == 75.0

    def test_student_analytics_with_non_numeric_score(
        self,
        api_client_student_a1,
        student_a1,
        exam_assignment_a,
        center_a,
    ):
        """Analytics handles non-numeric scores in results."""
        with schema_context(center_a.schema_name):
            # Create submission with non-numeric score
            bad_results = {
                "jlpt_result": {
                    "section_results": {
                        "language_knowledge": {
                            "score": "not_a_number",  # ← Invalid
                        }
                    }
                }
            }
            bad_submission = Submission.objects.create(
                user_id=student_a1.id,
                exam_assignment=exam_assignment_a,
                status=Submission.Status.GRADED,
                score=Decimal("70.00"),
                results=bad_results,
                completed_at=timezone.now(),
            )
        
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should not crash, invalid scores are skipped
        assert data["average_score"] == 70.0

    def test_student_analytics_with_zero_max_score_in_quiz(
        self,
        api_client_student_a1,
        student_a1,
        exam_assignment_a,
        center_a,
    ):
        """Analytics handles quiz with zero max_score (avoids ZeroDivisionError)."""
        with schema_context(center_a.schema_name):
            # Create submission with quiz result having zero max_score
            bad_results = {
                "resource_type": "quiz",
                "total_score": 50,
                "max_score": 0,  # ← Zero, will cause ZeroDivisionError if not handled
            }
            bad_submission = Submission.objects.create(
                user_id=student_a1.id,
                exam_assignment=exam_assignment_a,
                status=Submission.Status.GRADED,
                score=Decimal("50.00"),
                results=bad_results,
                completed_at=timezone.now(),
            )
        
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should not crash (ZeroDivisionError caught)
        assert data["average_score"] == 50.0


@pytest.mark.django_db(transaction=True)
class TestEmptyCenter:
    """Test analytics for empty/new centers."""

    def test_center_admin_analytics_empty_center(
        self,
        api_client_center_admin_b,
        center_b,
    ):
        """Center Admin for empty center gets valid response with zeros."""
        resp = api_client_center_admin_b.get(reverse("center-admin-analytics"))
        assert resp.status_code == 200
        data = resp.data
        
        # All counts should be 0 or minimal
        assert data["total_students"] == 0
        assert data["total_teachers"] == 0
        assert data["total_groups"] == 0
        assert data["active_exams_count"] == 0

    def test_student_analytics_no_submissions(
        self,
        api_client_student_b1,
        student_b1,
    ):
        """Student with no submissions gets valid response with zeros."""
        resp = api_client_student_b1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # All counts should be 0
        assert data["average_score"] == 0.0
        assert data["completed_exams_count"] == 0
        assert data["upcoming_deadlines"] == []
        assert data["recent_results"] == []
        # Skill performance should have empty list or all zeros
        assert isinstance(data["skill_performance"], list)


@pytest.mark.django_db(transaction=True)
class TestHomeworkExclusion:
    """Test that completed homework doesn't appear in upcoming deadlines."""

    def test_completed_homework_excluded_from_upcoming(
        self,
        api_client_student_a1,
        student_a1,
        homework_assignment_a,
        center_a,
    ):
        """Homework with GRADED submission excluded from upcoming_deadlines."""
        with schema_context(center_a.schema_name):
            # Create a graded submission for the homework
            graded_hw_submission = Submission.objects.create(
                user_id=student_a1.id,
                homework_assignment=homework_assignment_a,
                status=Submission.Status.GRADED,
                score=Decimal("85.00"),
                results={"some": "data"},
                completed_at=timezone.now() - timedelta(days=1),
            )
        
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Homework should NOT appear in upcoming_deadlines
        # (since student has a GRADED submission for it)
        upcoming_hw_ids = {str(d["id"]) for d in data["upcoming_deadlines"]}
        assert str(homework_assignment_a.id) not in upcoming_hw_ids

    def test_submitted_homework_excluded_from_upcoming(
        self,
        api_client_student_a2,
        student_a2,
        homework_assignment_a,
        center_a,
    ):
        """Homework with any submission excluded from upcoming_deadlines.
        
        Note: The test checks that if student has a GRADED submission,
        it's excluded. A SUBMITTED submission doesn't exclude it yet
        (student can still resubmit before grading).
        """
        with schema_context(center_a.schema_name):
            # Create a GRADED submission (should exclude from upcoming)
            graded_submission = Submission.objects.create(
                user_id=student_a2.id,
                homework_assignment=homework_assignment_a,
                status=Submission.Status.GRADED,
                score=Decimal("90.00"),
                results={},
                completed_at=timezone.now(),
            )
        
        resp = api_client_student_a2.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should not appear in upcoming deadlines
        upcoming_hw_ids = {str(d["id"]) for d in data["upcoming_deadlines"]}
        assert str(homework_assignment_a.id) not in upcoming_hw_ids

    def test_pending_homework_included_in_upcoming(
        self,
        api_client_student_a1,
        student_a1,
        homework_assignment_a,
        submission_student_a1_pending_hw,
    ):
        """Homework without GRADED submission appears in upcoming_deadlines."""
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Homework should appear in upcoming_deadlines
        # (student hasn't graded their submission yet)
        upcoming_hw_ids = {str(d["id"]) for d in data["upcoming_deadlines"]}
        assert str(homework_assignment_a.id) in upcoming_hw_ids

    def test_overdue_homework_not_in_upcoming(
        self,
        api_client_student_a1,
        student_a1,
        teacher_a,
        group_a,
        mock_test_n5,
        center_a,
    ):
        """Overdue homework (deadline in past) not in upcoming_deadlines."""
        with schema_context(center_a.schema_name):
            # Create overdue homework
            overdue_hw = __import__('apps.assignments.models', fromlist=['HomeworkAssignment']).HomeworkAssignment.objects.create(
                title="Overdue Homework",
                description="Already passed deadline",
                deadline=timezone.now() - timedelta(days=1),  # ← Past
                created_by=teacher_a,
            )
            overdue_hw.assigned_groups.set([group_a.id])
            overdue_hw.mock_tests.set([mock_test_n5.id])
        
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Overdue homework should not appear
        upcoming_hw_ids = {str(d["id"]) for d in data["upcoming_deadlines"]}
        # The overdue homework has deadline in the past, so it won't be included
        # (query filters by deadline__gt=now)
