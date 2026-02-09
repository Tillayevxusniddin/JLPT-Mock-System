"""
Comprehensive tests for Analytics dashboards.

Tests all dashboard endpoints for each role:
- Owner: Global dashboard
- CenterAdmin: Center-specific dashboard
- Teacher: Class-specific dashboard
- Student: Personal dashboard
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from unittest.mock import patch


@pytest.mark.django_db(transaction=True)
class TestOwnerAnalytics:
    """Owner dashboard tests."""

    def test_owner_dashboard_counts(
        self,
        api_client_owner,
        center_a,
        center_b,
        owner_user,
        contact_requests,
    ):
        """Owner dashboard returns total centers and recent contact requests."""
        resp = api_client_owner.get(reverse("analytics-owner"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should have at least 2 centers (A and B)
        assert data["total_centers"] >= 2
        
        # Should have contact requests
        assert data["active_centers_count"] >= 1
        assert len(data["recent_contact_requests"]) == 5
        
        # Verify contact request structure
        for cr in data["recent_contact_requests"]:
            assert "id" in cr
            assert "center_name" in cr
            assert "full_name" in cr
            assert cr["center_name"] == "Center A"

    def test_owner_dashboard_centers_breakdown(
        self,
        api_client_owner,
        center_a,
        center_b,
        owner_user,
    ):
        """Owner dashboard includes metrics for each center."""
        resp = api_client_owner.get(reverse("analytics-owner"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should have breakdown by center
        assert "centers_breakdown" in data
        assert len(data["centers_breakdown"]) >= 2

    def test_owner_dashboard_no_auth(self, api_client):
        """Unauthenticated request returns 401."""
        resp = api_client.get(reverse("analytics-owner"))
        assert resp.status_code == 401

    def test_owner_dashboard_forbidden_for_non_owner(self, api_client_center_admin_a):
        """Non-owner cannot access owner dashboard."""
        resp = api_client_center_admin_a.get(reverse("analytics-owner"))
        assert resp.status_code == 403

    @patch("apps.analytics.services.analytics_cache")
    def test_owner_dashboard_uses_cache(self, mock_cache, api_client_owner):
        """Owner dashboard uses cache for performance."""
        mock_cache.get.return_value = None
        mock_cache.set.return_value = None
        
        resp = api_client_owner.get(reverse("analytics-owner"))
        assert resp.status_code == 200
        
        # Verify cache was called
        mock_cache.get.assert_called()


@pytest.mark.django_db(transaction=True)
class TestCenterAdminAnalytics:
    """Center Admin dashboard tests."""

    def test_center_admin_dashboard_counts(
        self,
        api_client_center_admin_a,
        center_a,
        student_a1,
        student_a2,
        teacher_a,
        group_a,
        exam_assignment_a,
    ):
        """Center Admin dashboard returns counts for their center."""
        resp = api_client_center_admin_a.get(reverse("analytics-center-admin"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should count students in Center A
        assert data["total_students"] == 2  # student_a1, student_a2
        
        # Should count teachers in Center A
        assert data["total_teachers"] == 1  # teacher_a
        
        # Should count groups in tenant
        assert data["total_groups"] >= 1
        
        # Should count active exams
        assert data["active_exams_count"] >= 0

    def test_center_admin_dashboard_isolation(
        self,
        api_client_center_admin_a,
        api_client_center_admin_b,
        center_a,
        center_b,
        student_a1,
        student_b1,
    ):
        """Center Admin A sees only Center A's students, not Center B's."""
        resp_a = api_client_center_admin_a.get(reverse("analytics-center-admin"))
        resp_b = api_client_center_admin_b.get(reverse("analytics-center-admin"))
        
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        
        # Both see their respective student counts
        assert resp_a.data["total_students"] == 2  # Center A has 2
        assert resp_b.data["total_students"] == 1  # Center B has 1

    def test_center_admin_dashboard_forbidden_for_non_admin(
        self,
        api_client_student_a1,
    ):
        """Student cannot access center admin dashboard."""
        resp = api_client_student_a1.get(reverse("analytics-center-admin"))
        assert resp.status_code == 403


@pytest.mark.django_db(transaction=True)
class TestTeacherAnalytics:
    """Teacher dashboard tests."""

    def test_teacher_dashboard_groups_and_students(
        self,
        api_client_teacher_a,
        teacher_a,
        group_a,
        student_a1,
        student_a2,
        group_membership_teacher_a,
        group_membership_student_a1,
        group_membership_student_a2,
    ):
        """Teacher sees their groups and students."""
        resp = api_client_teacher_a.get(reverse("analytics-teacher"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should have 1 group
        assert data["my_groups_count"] >= 1
        
        # Should have 2 students in their group(s)
        assert data["total_students"] == 2

    def test_teacher_dashboard_pending_grading(
        self,
        api_client_teacher_a,
        teacher_a,
        group_a,
        student_a2,
        submission_student_a2_submitted,
        group_membership_teacher_a,
        group_membership_student_a2,
    ):
        """Teacher dashboard shows pending submissions for grading."""
        resp = api_client_teacher_a.get(reverse("analytics-teacher"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should have 1 submission in SUBMITTED status pending grading
        assert data["pending_grading_count"] >= 1

    def test_teacher_dashboard_recent_submissions_with_names(
        self,
        api_client_teacher_a,
        teacher_a,
        group_a,
        student_a1,
        student_a2,
        exam_assignment_a,
        submission_student_a1_1,
        submission_student_a2_graded,
        group_membership_teacher_a,
        group_membership_student_a1,
        group_membership_student_a2,
    ):
        """Teacher dashboard resolves student names from public schema."""
        resp = api_client_teacher_a.get(reverse("analytics-teacher"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should have recent submissions
        assert len(data["recent_submissions"]) >= 1
        
        # Verify submission structure and name resolution
        for sub in data["recent_submissions"]:
            assert "id" in sub
            assert "student_name" in sub
            assert "assignment_title" in sub
            assert "score" in sub
            assert "submitted_at" in sub
            # Student name should be resolved (not empty, not just ID)
            assert sub["student_name"] != ""

    def test_teacher_dashboard_no_groups(
        self,
        api_client_teacher_b,
    ):
        """Teacher with no groups returns empty analytics."""
        resp = api_client_teacher_b.get(reverse("analytics-teacher"))
        assert resp.status_code == 200
        data = resp.data
        
        assert data["my_groups_count"] == 0
        assert data["total_students"] == 0
        assert data["pending_grading_count"] == 0
        assert data["recent_submissions"] == []

    def test_teacher_dashboard_forbidden_for_non_teacher(
        self,
        api_client_student_a1,
    ):
        """Student cannot access teacher dashboard."""
        resp = api_client_student_a1.get(reverse("analytics-teacher"))
        assert resp.status_code == 403


@pytest.mark.django_db(transaction=True)
class TestStudentAnalytics:
    """Student dashboard tests."""

    def test_student_dashboard_average_score(
        self,
        api_client_student_a1,
        student_a1,
        submission_student_a1_1,
        submission_student_a1_2,
        submission_student_a1_3,
    ):
        """Student dashboard calculates average score correctly."""
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Student A1 has scores: 150, 145, 155
        # Average: (150 + 145 + 155) / 3 = 150.0
        expected_avg = round((150 + 145 + 155) / 3, 2)
        assert data["average_score"] == expected_avg
        assert data["completed_exams_count"] == 3

    def test_student_dashboard_average_score_zero_when_no_submissions(
        self,
        api_client_student_b1,
        student_b1,
    ):
        """Student with no graded submissions gets average_score of 0.0."""
        resp = api_client_student_b1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        assert data["average_score"] == 0.0
        assert data["completed_exams_count"] == 0

    def test_student_dashboard_skill_performance(
        self,
        api_client_student_a1,
        student_a1,
        submission_student_a1_1,
        submission_student_a1_2,
        submission_student_a1_3,
    ):
        """Student dashboard aggregates skill performance from JLPT results."""
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should have skill performance data
        assert len(data["skill_performance"]) > 0
        
        # Verify skill names are correct
        skill_names = {skill["skill_name"] for skill in data["skill_performance"]}
        assert "Vocabulary" in skill_names  # language_knowledge
        assert "Reading" in skill_names
        assert "Listening" in skill_names
        
        # Verify scores are averaged
        # Vocab scores: 60, 55, 58 → avg = 57.67
        vocab_skill = next(
            (s for s in data["skill_performance"] if s["skill_name"] == "Vocabulary"),
            None,
        )
        assert vocab_skill is not None
        expected_vocab = round((60 + 55 + 58) / 3, 2)
        assert vocab_skill["average_score"] == expected_vocab
        
        # Reading scores: 50, 48, 52 → avg = 50.0
        reading_skill = next(
            (s for s in data["skill_performance"] if s["skill_name"] == "Reading"),
            None,
        )
        assert reading_skill is not None
        expected_reading = round((50 + 48 + 52) / 3, 2)
        assert reading_skill["average_score"] == expected_reading
        
        # Listening scores: 40, 42, 45 → avg = 42.33
        listening_skill = next(
            (s for s in data["skill_performance"] if s["skill_name"] == "Listening"),
            None,
        )
        assert listening_skill is not None
        expected_listening = round((40 + 42 + 45) / 3, 2)
        assert listening_skill["average_score"] == expected_listening

    def test_student_dashboard_upcoming_deadlines(
        self,
        api_client_student_a1,
        student_a1,
        homework_assignment_a,
        group_membership_student_a1,
    ):
        """Student dashboard shows upcoming homework deadlines."""
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should have upcoming deadlines (homework not yet submitted)
        assert len(data["upcoming_deadlines"]) >= 1
        
        # Verify deadline structure
        for deadline in data["upcoming_deadlines"]:
            assert "id" in deadline
            assert "title" in deadline
            assert "deadline" in deadline
            assert "type" in deadline
            assert deadline["type"] == "Homework"

    def test_student_dashboard_recent_results(
        self,
        api_client_student_a1,
        student_a1,
        submission_student_a1_1,
        submission_student_a1_2,
        submission_student_a1_3,
    ):
        """Student dashboard shows recent graded submissions."""
        resp = api_client_student_a1.get(reverse("analytics-student"))
        assert resp.status_code == 200
        data = resp.data
        
        # Should have recent results
        assert len(data["recent_results"]) >= 1
        
        # Verify result structure
        for result in data["recent_results"]:
            assert "id" in result
            assert "assignment_title" in result
            assert "score" in result
            assert "status" in result
            assert result["status"] == "GRADED"

    def test_student_dashboard_forbidden_for_non_student(
        self,
        api_client_teacher_a,
    ):
        """Teacher cannot access student dashboard."""
        resp = api_client_teacher_a.get(reverse("analytics-student"))
        assert resp.status_code == 403
