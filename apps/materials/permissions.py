# apps/materials/permissions.py
from rest_framework import permissions

class IsAdminOrTeacher(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in {"CENTER_ADMIN", "TEACHER"}


class IsMaterialOwnerOrCenterAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.role in {"CENTER_ADMIN"}:
            return True

        if user.role in {"TEACHER"}:
            return obj.created_by_id == user.id

        return False
        