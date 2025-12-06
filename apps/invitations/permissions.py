"""
Custom permissions for invitations app
"""
from rest_framework import permissions


class IsCenterAdmin(permissions.BasePermission):
    """
    Permission to allow only CenterAdmin users
    """
    message = "Only Center Administrators can perform this action."
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'CENTERADMIN'
        )


class IsOrganizationMember(permissions.BasePermission):
    """
    Permission to check if user belongs to the same organization as the object
    """
    message = "You can only access resources from your own organization."
    
    def has_object_permission(self, request, view, obj):
        # Owner has access to all
        if request.user.role == 'OWNER':
            return True
        
        # Check if object has organization attribute
        if hasattr(obj, 'organization'):
            return obj.organization == request.user.organization
        
        return False


class CanManageInvitations(permissions.BasePermission):
    """
    Permission to check if user can manage invitations
    - ONLY CenterAdmin can manage invitations for their organization
    - Owner CANNOT interfere with organization's invitation system
    """
    message = "Only Center Administrators can manage invitations for their organization."
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Only CenterAdmin can manage invitations
        return request.user.role == 'CENTERADMIN'
