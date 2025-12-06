from rest_framework import generics, permissions
from .models import Organization
from .serializers import OrganizationSerializer, OrganizationListSerializer
from .permissions import IsOwner, IsOwnerOrCenterAdmin, CanManageOwnOrganization


class OrganizationListView(generics.ListAPIView):
    """
    List organizations
    - Owner sees all organizations
    - CenterAdmin sees only their organization
    """
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrCenterAdmin]
    
    def get_serializer_class(self):
        # Use lightweight serializer for lists
        return OrganizationListSerializer
    
    def get_queryset(self):
        user = self.request.user
        
        # Owner can see all organizations
        if user.role == 'OWNER':
            return Organization.objects.all().order_by('-created_at')
        
        # CenterAdmin sees only their organization
        if user.role == 'CENTERADMIN' and user.organization:
            return Organization.objects.filter(pk=user.organization.pk)
        
        return Organization.objects.none()

class OrganizationDetailView(generics.RetrieveAPIView):
    """
    Retrieve organization details
    - Owner can view any organization
    - CenterAdmin can only view their own organization
    """
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrCenterAdmin, CanManageOwnOrganization]

class OrganizationUpdateView(generics.UpdateAPIView):
    """
    Update organization
    - Owner can update any organization
    - CenterAdmin can only update their own organization
    """
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrCenterAdmin, CanManageOwnOrganization]

class OrganizationCreateView(generics.CreateAPIView):
    """
    Create new organization (tenant)
    - Only Owner can create organizations
    """
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]