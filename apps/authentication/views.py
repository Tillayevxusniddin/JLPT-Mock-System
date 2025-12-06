from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model

from apps.core.throttling import AuthenticationThrottle, PasswordResetThrottle
from .serializers import (
    RegisterSerializer, CustomTokenObtainPairSerializer, 
    UserSerializer, UserListSerializer, UserDetailSerializer,
    UserProfileUpdateSerializer,
    PasswordChangeSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer
)

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    serializer_class = RegisterSerializer
    throttle_classes = [AuthenticationThrottle]

class LoginView(TokenObtainPairView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [AuthenticationThrottle]

class MeView(APIView):
    """Joriy user ma'lumotlarini olish va yangilash"""
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        serializer = UserDetailSerializer(request.user, context={'request': request})
        return Response(serializer.data)
    
    def put(self, request):
        """Full profile update"""
        serializer = UserProfileUpdateSerializer(
            request.user, 
            data=request.data, 
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Return full user details after update
        return Response(
            UserDetailSerializer(request.user, context={'request': request}).data
        )
    
    def patch(self, request):
        """Partial profile update"""
        serializer = UserProfileUpdateSerializer(
            request.user, 
            data=request.data, 
            partial=True,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Return full user details after update
        return Response(
            UserDetailSerializer(request.user, context={'request': request}).data
        )
    
class PendingUsersListView(generics.ListAPIView):
    """Tasdiqlashni kutayotgan userlar ro'yxati (Faqat CenterAdmin uchun)"""
    serializer_class = UserListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Faqat o'zining organizatsiyasidagi va approved=False bo'lganlarni ko'radi
        if self.request.user.is_center_admin:
            return User.objects.filter(
                organization=self.request.user.organization,
                is_approved=False
            ).select_related('organization')
        return User.objects.none()

class ApproveUserView(APIView):
    """Userni tasdiqlash"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not request.user.is_center_admin:
            return Response({"error": "Ruxsat yo'q"}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            user = User.objects.get(pk=pk, organization=request.user.organization)
            user.is_approved = True
            user.save()
            return Response({"status": "User approved", "user_id": user.id})
        except User.DoesNotExist:
            return Response({"error": "User topilmadi"}, status=status.HTTP_404_NOT_FOUND)


class LogoutView(APIView):
    """Blacklist refresh token on logout"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh_token")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            token = RefreshToken(refresh_token)
            token.blacklist()
            
            return Response(
                {"detail": "Successfully logged out"},
                status=status.HTTP_205_RESET_CONTENT
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class PasswordChangeView(APIView):
    """Change password for authenticated user"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"detail": "Password changed successfully"},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetRequestView(APIView):
    """Request password reset via email"""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetThrottle]
    
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            # Always return success to prevent email enumeration
            return Response(
                {"detail": "If email exists, reset link has been sent"},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmView(APIView):
    """Confirm password reset with token"""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetThrottle]
    
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"detail": "Password has been reset successfully"},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)