# api/v1/auth_urls.py
from django.urls import path

from apps.authentication.views import (
    RegisterView,
    LoginView,
    MeView,
    LogoutView,
    UpdatePasswordView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    UserAvatarUploadView,
)

app_name = "auth"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("me/", MeView.as_view(), name="me"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("password/update/", UpdatePasswordView.as_view(), name="password-update"),
    path("password/reset/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password/reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("avatar/", UserAvatarUploadView.as_view(), name="avatar-upload"),
]
