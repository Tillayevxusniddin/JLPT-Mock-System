"""
Custom permissions for organizations app
"""
from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """
    Permission to allow only Owner (platform admin) users
    """
    message = "Only Platform Owner can perform this action."
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'OWNER'
        )


class IsOwnerOrCenterAdmin(permissions.BasePermission):
    """
    Permission to allow Owner or CenterAdmin users
    """
    message = "Only Owner or Center Admin can perform this action."
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in ['OWNER', 'CENTERADMIN']
        )


class CanManageOwnOrganization(permissions.BasePermission):
    """
    Permission to check if user can manage their own organization
    - Owner can manage all organizations
    - CenterAdmin can only manage their own organization
    """
    message = "You can only manage your own organization."
    
    def has_object_permission(self, request, view, obj):
        # Owner has access to all organizations
        if request.user.role == 'OWNER':
            return True
        
        # CenterAdmin can only manage their own organization
        if request.user.role == 'CENTERADMIN':
            return obj == request.user.organization
        
        return False
