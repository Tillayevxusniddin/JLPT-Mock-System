from django.contrib import admin
from .models import Group, GroupTeacher, GroupMembership


class TenantAdminMixin:
    """
    ✅ Mixin to restrict OWNER role from accessing tenant-specific admin models.
    
    Security Rationale:
    - OWNER role manages organizations in the public schema
    - OWNER should NEVER access tenant data (groups, students, etc.)
    - Only CENTERADMIN, TEACHER roles should access tenant admin
    """
    
    def has_module_permission(self, request):
        """Hide tenant models from OWNER in admin sidebar"""
        user = request.user
        
        # ✅ Block OWNER from seeing tenant modules
        if user.role == 'OWNER':
            return False
        
        # ✅ Only allow authenticated users from tenant roles
        return user.is_authenticated and user.role in ['CENTERADMIN', 'TEACHER']
    
    def has_view_permission(self, request, obj=None):
        """Allow viewing tenant objects"""
        if request.user.role == 'OWNER':
            return False
        return super().has_view_permission(request, obj)
    
    def has_add_permission(self, request):
        """Allow adding tenant objects"""
        if request.user.role == 'OWNER':
            return False
        # Only CENTERADMIN can create groups
        return request.user.role == 'CENTERADMIN'
    
    def has_change_permission(self, request, obj=None):
        """Allow changing tenant objects"""
        if request.user.role == 'OWNER':
            return False
        # Only CENTERADMIN can edit groups
        return request.user.role == 'CENTERADMIN'
    
    def has_delete_permission(self, request, obj=None):
        """Allow deleting tenant objects"""
        if request.user.role == 'OWNER':
            return False
        # Only CENTERADMIN can delete groups
        return request.user.role == 'CENTERADMIN'


class GroupTeacherInline(admin.TabularInline):
    model = GroupTeacher
    extra = 1
    fields = ('teacher_id', 'is_primary', 'assigned_at')
    readonly_fields = ('assigned_at',)


class GroupMembershipInline(admin.TabularInline):
    model = GroupMembership
    extra = 0
    fields = ('student_id', 'status', 'joined_at')
    readonly_fields = ('joined_at',)


@admin.register(Group)
class GroupAdmin(TenantAdminMixin, admin.ModelAdmin):
    """
    ✅ Admin interface for Group model with tenant isolation.
    """
    list_display = ('name', 'level', 'student_count', 'max_students', 'is_active', 'created_at')
    list_filter = ('level', 'is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('id', 'student_count', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'description', 'level')
        }),
        ('Capacity', {
            'fields': ('max_students', 'student_count', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [GroupTeacherInline, GroupMembershipInline]


@admin.register(GroupTeacher)
class GroupTeacherAdmin(TenantAdminMixin, admin.ModelAdmin):
    """Admin interface for GroupTeacher assignments"""
    list_display = ('group', 'teacher_id', 'is_primary', 'assigned_at')
    list_filter = ('is_primary', 'assigned_at')
    search_fields = ('group__name',)


@admin.register(GroupMembership)
class GroupMembershipAdmin(TenantAdminMixin, admin.ModelAdmin):
    """Admin interface for GroupMembership"""
    list_display = ('group', 'student_id', 'status', 'joined_at')
    list_filter = ('status', 'joined_at')
    search_fields = ('group__name',)
