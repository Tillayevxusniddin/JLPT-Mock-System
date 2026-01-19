from rest_framework import permissions
from django.conf import settings

class IsOwner(permissions.BasePermission):
    message = "Only platform owners can perform this action."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "OWNER"

class IsCenterAdmin(permissions.BasePermission):
    message = "Only center admins can perform this action."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "CENTER_ADMIN"

class IsTeacher(permissions.BasePermission):
    message = "Only teachers can perform this action."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.role == "TEACHER":
            return True
        if request.user.role == "CENTER_ADMIN" and getattr(view, "allow_admin", False):
            return True
        return False

class IsCenterAdminOrTeacher(permissions.BasePermission):
    message = "Only center admins or teachers can perform this action."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ["CENTER_ADMIN", "TEACHER"]

class IsStudent(permissions.BasePermission):
    message = "Only students can perform this action."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "STUDENT"

class IsOwnerOrCenterAdmin(permissions.BasePermission):
    message = "Only Owner or Center Admins can perform this action."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ["OWNER", "CENTER_ADMIN"]