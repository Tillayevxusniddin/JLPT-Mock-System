#apps/analytics/serializers.py
from rest_framework import serializers


class RecentSubmissionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    student_name = serializers.CharField()
    assignment_title = serializers.CharField()
    score = serializers.FloatField(allow_null=True)
    submitted_at = serializers.DateTimeField(allow_null=True)


class UpcomingDeadlineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    deadline = serializers.DateTimeField()
    type = serializers.CharField()  # "Exam" or "Homework"


class SkillPerformanceSerializer(serializers.Serializer):
    skill_name = serializers.CharField()
    average_score = serializers.FloatField()


class RecentResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    assignment_title = serializers.CharField()
    score = serializers.FloatField(allow_null=True)
    status = serializers.CharField()
    completed_at = serializers.DateTimeField(allow_null=True)


class OwnerAnalyticsSerializer(serializers.Serializer):
    total_centers = serializers.IntegerField()
    total_users = serializers.IntegerField()
    active_centers_count = serializers.IntegerField()
    recent_contact_requests = serializers.ListField(child=serializers.DictField())


class CenterAdminAnalyticsSerializer(serializers.Serializer):
    total_students = serializers.IntegerField()
    total_teachers = serializers.IntegerField()
    total_groups = serializers.IntegerField()
    active_exams_count = serializers.IntegerField()


class TeacherAnalyticsSerializer(serializers.Serializer):
    my_groups_count = serializers.IntegerField()
    total_students = serializers.IntegerField()
    pending_grading_count = serializers.IntegerField()
    recent_submissions = RecentSubmissionSerializer(many=True)


class StudentAnalyticsSerializer(serializers.Serializer):
    average_score = serializers.FloatField()
    completed_exams_count = serializers.IntegerField()
    upcoming_deadlines = UpcomingDeadlineSerializer(many=True)
    recent_results = RecentResultSerializer(many=True)
    skill_performance = SkillPerformanceSerializer(many=True)

