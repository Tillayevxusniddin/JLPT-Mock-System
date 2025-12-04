from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Invitation
from .serializers import InvitationCreateSerializer, CheckInvitationSerializer

class InvitationCreateView(generics.CreateAPIView):
    """
    Faqat CENTERADMIN o'z organizatsiyasi uchun kod yarata oladi.
    """
    serializer_class = InvitationCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        # User rostdan ham CenterAdmin ekanligini tekshirish kerak
        if not self.request.user.is_center_admin:
             from rest_framework.exceptions import PermissionDenied
             raise PermissionDenied("Faqat Center Adminlar taklifnoma yarata oladi.")
        serializer.save()

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