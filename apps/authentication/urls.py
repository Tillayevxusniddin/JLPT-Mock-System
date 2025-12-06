from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView, LoginView, MeView, 
    PendingUsersListView, ApproveUserView, LogoutView,
    PasswordChangeView, PasswordResetRequestView, PasswordResetConfirmView
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', MeView.as_view(), name='me'),
    path('password-change/', PasswordChangeView.as_view(), name='password-change'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('pending-users/', PendingUsersListView.as_view(), name='pending-users'),
    path('approve-user/<uuid:pk>/', ApproveUserView.as_view(), name='approve-user'),
]