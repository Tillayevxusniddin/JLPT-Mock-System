"""
Custom throttle classes for rate limiting
"""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthenticationThrottle(AnonRateThrottle):
    """
    Throttle for authentication endpoints (login, register)
    Prevents brute force attacks
    """
    rate = '10/minute'
    scope = 'auth'


class PasswordResetThrottle(AnonRateThrottle):
    """
    Throttle for password reset requests
    Prevents abuse of password reset functionality
    """
    rate = '5/hour'
    scope = 'password_reset'


class GroupOperationThrottle(UserRateThrottle):
    """
    ✅ Rate limiting for group operations to prevent abuse.
    
    Limits:
    - 100 requests per hour for authenticated users
    - Applied to: Group create/update/delete, add_member, remove_member
    
    Security Rationale:
    - Prevents rapid creation of groups (resource exhaustion)
    - Prevents spam in add_member/remove_member operations
    - Protects database from excessive write operations
    """
    scope = 'group_operations'
    rate = '100/hour'


class InvitationThrottle(UserRateThrottle):
    """
    ✅ Rate limiting for invitation creation to prevent spam.
    
    Limits:
    - 50 invitations per hour per user
    - Applied to: Invitation create endpoint
    
    Security Rationale:
    - Prevents invitation spam attacks
    - Protects email service from abuse
    - Prevents database bloat from excessive invitations
    """
    scope = 'invitations'
    rate = '50/hour'


class AssignmentOperationThrottle(UserRateThrottle):
    """
    ✅ Rate limiting for assignment operations.
    
    Limits:
    - 200 requests per hour for assignment operations
    - Applied to: Assignment create/update/delete
    
    Security Rationale:
    - Prevents rapid creation of assignments
    - Protects against DoS via assignment spam
    """
    scope = 'assignment_operations'
    rate = '200/hour'
