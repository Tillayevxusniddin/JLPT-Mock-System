#apps/groups/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from apps.core.models import TenantBaseModel 

class Group(TenantBaseModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    max_students = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True, db_index=True)
    student_count = models.PositiveIntegerField(default=0)
    teacher_count = models.PositiveIntegerField(default=0)
    avatar = models.ImageField(upload_to="group_avatars/", null=True, blank=True)
    
    class Meta:
        db_table = 'groups'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['name'], name='unique_group_name')
        ]
    
    def __str__(self):
        return self.name

class GroupMembership(TenantBaseModel):
    """Membership of a user in a group with a role (student or teacher)."""

    ROLE_STUDENT = "STUDENT"
    ROLE_TEACHER = "TEACHER"
    ROLE_IN_GROUP_CHOICES = [(ROLE_STUDENT, "Student"), (ROLE_TEACHER, "Teacher")]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='memberships')
    user_id = models.BigIntegerField(db_index=True)
    role_in_group = models.CharField(max_length=20, choices=ROLE_IN_GROUP_CHOICES)

    class Meta: 
        unique_together = ("user_id", "group", "role_in_group") 
        indexes = [ 
            models.Index(fields=['user_id', 'group', 'role_in_group']),
            models.Index(fields=['user_id', 'role_in_group']), 
            models.Index(fields=['group', 'role_in_group']), 
        ]

    HARD_DELETE = True
    objects = models.Manager()
    all_objects = models.Manager()

    def __str__(self): 
        return f"User {self.user_id} in {self.group} as {self.role_in_group}"

    

class GroupMembershipHistory(models.Model):
    user_id = models.BigIntegerField(db_index=True)
    group = models.ForeignKey("groups.Group", on_delete=models.CASCADE, related_name="membership_history")
    role_in_group = models.CharField(max_length=20, choices=GroupMembership.ROLE_IN_GROUP_CHOICES)
    joined_at = models.DateTimeField()
    left_at = models.DateTimeField(auto_now_add=True)

    left_reason = models.CharField(
        max_length=20,
        choices=[
            ("MOVED", "Moved to another group"),
            ("REMOVED", "Removed by admin"),
            ("LEFT", "Left voluntarily"),
        ],
    )
    class Meta:
        indexes = [
            models.Index(fields=['user_id', 'left_at']),
            models.Index(fields=['group', 'left_at']),
        ]
    
