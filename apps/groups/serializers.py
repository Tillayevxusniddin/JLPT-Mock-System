# apps/groups/serializers.py

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from django.db import transaction

from apps.groups.models import Group, GroupMembership
from apps.authentication.models import User
from apps.authentication.serializers import SimpleUserSerializer


class GroupListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing groups.
    Includes teacher details fetched from Public Schema.
    
    OPTIMIZATION: Uses pre-fetched teacher_map from context when available
    to eliminate N+1 schema switching.
    """
    teachers = serializers.SerializerMethodField()
    
    class Meta:
        model = Group
        fields = [
            "id", "name", "description", "avatar", 
            "is_active", "student_count", "teacher_count", 
            "teachers", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "student_count", "teacher_count", "created_at", "updated_at"]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_teachers(self, obj):
        """
        Get teacher details for this group.
        
        Performance optimization:
        - If teacher_map exists in context (list view), use it (zero DB hits, zero schema switches)
        - Otherwise, fall back to fetching from DB (detail view or legacy code)
        """
        # OPTIMIZATION: Check if we have pre-fetched teachers in context
        teacher_map = self.context.get('teacher_map')
        if teacher_map is not None:
            # Fast path: Return pre-fetched data (no DB query, no schema switch!)
            return teacher_map.get(str(obj.id), [])
        
        # FALLBACK: Original logic for detail views or when context pre-fetching not used
        try:
            # 1. Get Teacher IDs from Tenant Schema
            teacher_ids = list(
                GroupMembership.objects.filter(
                    group=obj, 
                    role_in_group="TEACHER"
                ).values_list('user_id', flat=True)
            )
            
            if not teacher_ids:
                return []

            # 2. Get User details from Public Schema
            from apps.core.tenant_utils import with_public_schema
            
            def get_teacher_users():
                users = User.objects.filter(id__in=teacher_ids)
                return SimpleUserSerializer(users, many=True).data
            
            return with_public_schema(get_teacher_users)
            
        except Exception:
            return []



class GroupSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating groups.
    Allows assigning teachers during creation.
    """
    teacher_ids = serializers.ListField(
        child=serializers.IntegerField(), 
        write_only=True, 
        required=False,
        help_text="List of User IDs to assign as teachers immediately."
    )
    teachers = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Group
        fields = [
            "id", "name", "description", "avatar", "max_students", 
            "is_active", "teacher_ids", "teachers", 
            "student_count", "teacher_count",
            "created_at", "updated_at"
        ]
        read_only_fields = ["id", "student_count", "teacher_count", "created_at", "updated_at"]

    def validate_teacher_ids(self, value):
        if not value:
            return value
            
        from apps.core.tenant_utils import with_public_schema
        
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError("Request context required.")

        def validate_users():
            users = list(User.objects.filter(id__in=value))
            if len(users) != len(set(value)):
                raise serializers.ValidationError("Some users were not found.")
            
            for user in users:
                if user.center_id != request.user.center_id:
                    raise serializers.ValidationError(f"User {user.id} belongs to another center.")
                if user.role != "TEACHER":
                    raise serializers.ValidationError(f"User {user.id} is not a TEACHER.")
            return True

        with_public_schema(validate_users)
        return value

    def create(self, validated_data):
        teacher_ids = validated_data.pop('teacher_ids', [])
        
        with transaction.atomic():
            group = super().create(validated_data)
            
            if teacher_ids:
                memberships = [
                    GroupMembership(
                        group=group,
                        user_id=tid,
                        role_in_group="TEACHER"
                    ) for tid in teacher_ids
                ]
                GroupMembership.objects.bulk_create(memberships)
                
                # Update count manually since bulk_create doesn't trigger signals
                group.teacher_count = len(teacher_ids)
                group.save(update_fields=['teacher_count'])
                
        return group

    def get_teachers(self, obj):
        return GroupListSerializer(obj).get_teachers(obj)


class GroupMembershipSerializer(serializers.ModelSerializer):
    """
    Serializer for managing individual group memberships.
    """
    user_id = serializers.IntegerField()
    group_id = serializers.UUIDField()

    class Meta:
        model = GroupMembership
        fields = ["id", "user_id", "group_id", "role_in_group", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_user_id(self, value):
        from apps.core.tenant_utils import with_public_schema
        try:
            with_public_schema(lambda: User.objects.get(id=value))
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")
        return value
    
    def validate_group_id(self, value):
        if not Group.objects.filter(id=value).exists():
            raise serializers.ValidationError("Group not found.")
        return value

    def validate(self, attrs):
        from apps.core.tenant_utils import with_public_schema
        
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError("Request context required.")
            
        actor = request.user
        
        def get_target_user():
            return User.objects.get(id=attrs["user_id"])
        target_user = with_public_schema(get_target_user)

        if target_user.center_id != actor.center_id:
            raise serializers.ValidationError("User belongs to a different center.")

        role_in_group = attrs["role_in_group"]
        
        if role_in_group == "TEACHER" and target_user.role != "TEACHER":
             raise serializers.ValidationError("User role must be TEACHER to be added as a teacher.")
             
        if role_in_group == "STUDENT" and target_user.role not in ["STUDENT", "GUEST"]:
             raise serializers.ValidationError("User role must be STUDENT or GUEST.")

        return attrs

    def create(self, validated_data):
        from django.db import IntegrityError
        try:
            return super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError({
                "detail": "This user is already a member of this group with this role."
            })


class BulkGroupMembershipSerializer(serializers.Serializer):
    """
    Serializer for bulk adding members to a group.
    Ensures data integrity with transaction.atomic.
    """
    group_id = serializers.UUIDField()
    members = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        max_length=100,
        help_text="[{'user_id': 1, 'role_in_group': 'STUDENT'}, ...]"
    )

    def validate(self, attrs):
        from apps.core.tenant_utils import with_public_schema
        
        request = self.context.get("request")
        actor = request.user
        
        try:
            group = Group.objects.get(id=attrs["group_id"])
        except Group.DoesNotExist:
            raise serializers.ValidationError("Group not found.")
            
        members_data = attrs["members"]
        user_ids = [m.get('user_id') for m in members_data]
        
        def validate_users():
            users = User.objects.filter(id__in=user_ids)
            if users.count() != len(set(user_ids)):
                raise serializers.ValidationError("Some users not found.")
            
            user_map = {u.id: u for u in users}
            for u in users:
                if u.center_id != actor.center_id:
                    raise serializers.ValidationError(f"User {u.id} belongs to different center.")
            return user_map
            
        user_map = with_public_schema(validate_users)

        for m in members_data:
            uid = m.get('user_id')
            role = m.get('role_in_group')
            user = user_map.get(uid)
            
            if role == "TEACHER" and user.role != "TEACHER":
                raise serializers.ValidationError(f"User {uid} is not a TEACHER.")
            if role == "STUDENT" and user.role not in ["STUDENT", "GUEST"]:
                raise serializers.ValidationError(f"User {uid} cannot be added as STUDENT.")
                
        return attrs

    def create(self, validated_data):
        group_id = validated_data["group_id"]
        members_data = validated_data["members"]
        
        existing_users = set(GroupMembership.objects.filter(
            group_id=group_id
        ).values_list('user_id', flat=True))
        
        new_memberships = []
        created_ids = []
        
        for m in members_data:
            if m['user_id'] not in existing_users:
                new_memberships.append(GroupMembership(
                    group_id=group_id,
                    user_id=m['user_id'],
                    role_in_group=m['role_in_group']
                ))
                created_ids.append(m['user_id'])
                existing_users.add(m['user_id']) 
        
        # TRANSACTION BLOCK (Critical Fix)
        with transaction.atomic():
            if new_memberships:
                GroupMembership.objects.bulk_create(new_memberships)
                
                # Lock group row to prevent race conditions during count update
                group = Group.objects.select_for_update().get(id=group_id)
                group.student_count = GroupMembership.objects.filter(group=group, role_in_group="STUDENT").count()
                group.teacher_count = GroupMembership.objects.filter(group=group, role_in_group="TEACHER").count()
                group.save(update_fields=['student_count', 'teacher_count'])
            
        return {
            "group_id": group_id,
            "created_count": len(new_memberships),
            "skipped_count": len(members_data) - len(new_memberships),
            "created_user_ids": created_ids
        }