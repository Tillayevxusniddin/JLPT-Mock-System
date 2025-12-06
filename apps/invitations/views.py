from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q

from apps.core.throttling import InvitationThrottle
from .models import Invitation
from .serializers import InvitationCreateSerializer, CheckInvitationSerializer, InvitationSerializer
from .permissions import CanManageInvitations


class InvitationListView(generics.ListAPIView):
    """
    List invitations for the user's organization
    - ONLY CenterAdmin can see their organization's invitations
    - Owner cannot access invitation system (organization internal matter)
    """
    serializer_class = InvitationSerializer
    permission_classes = [permissions.IsAuthenticated, CanManageInvitations]
    
    def get_queryset(self):
        user = self.request.user
        
        # Only CenterAdmin can access invitation list
        if user.role == 'CENTERADMIN' and user.organization:
            return Invitation.objects.filter(
                organization=user.organization
            ).select_related('organization', 'created_by')
        
        return Invitation.objects.none()


class InvitationCreateView(generics.CreateAPIView):
    """
    Create invitation codes
    - ONLY CenterAdmin can create invitations for their organization
    - Owner cannot interfere with organization's invitation system
    - ✅ Rate limited to 50 invitations/hour to prevent spam
    """
    serializer_class = InvitationCreateSerializer
    permission_classes = [permissions.IsAuthenticated, CanManageInvitations]
    throttle_classes = [InvitationThrottle]

    def perform_create(self, serializer):
        serializer.save()


class InvitationDetailView(generics.RetrieveAPIView):
    """
    Get invitation details
    - ONLY CenterAdmin can view their organization's invitations
    - Owner cannot access invitation details
    """
    serializer_class = InvitationSerializer
    permission_classes = [permissions.IsAuthenticated, CanManageInvitations]
    
    def get_queryset(self):
        user = self.request.user
        
        # Only CenterAdmin can view invitation details
        if user.role == 'CENTERADMIN' and user.organization:
            return Invitation.objects.filter(
                organization=user.organization
            ).select_related('organization', 'created_by')
        
        return Invitation.objects.none()


class InvitationUpdateView(generics.UpdateAPIView):
    """
    Update invitation (toggle is_active, update expires_at, etc.)
    - ONLY CenterAdmin can update their organization's invitations
    - Owner cannot interfere with organization's invitation system
    """
    serializer_class = InvitationSerializer
    permission_classes = [permissions.IsAuthenticated, CanManageInvitations]
    
    def get_queryset(self):
        user = self.request.user
        
        # Only CenterAdmin can update invitations
        if user.role == 'CENTERADMIN' and user.organization:
            return Invitation.objects.filter(organization=user.organization)
        
        return Invitation.objects.none()


class CheckInvitationView(APIView):
    """
    Public API: User registratsiyadan oldin kod to'g'riligini tekshirishi uchun
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = CheckInvitationSerializer(data=request.data)
        if serializer.is_valid():
            invite = Invitation.objects.get(code=request.data['code'])
            
            return Response({
                "valid": True,
                "organization": invite.organization.name,
                "role": invite.role
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)