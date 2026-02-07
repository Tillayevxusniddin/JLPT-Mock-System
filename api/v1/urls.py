#api/v1/urls.py
from django.urls import path, include

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
from apps.analytics.views import (
    OwnerAnalyticsView,
    CenterAdminAnalyticsView,
    TeacherAnalyticsView,
    StudentAnalyticsView,
)
from apps.centers.views import (
    InvitationCreateView,
    InvitationListView,
    InvitationApproveView,
    CenterCreateView,
    CenterAdminCreateView,
    CenterAvatarUploadView,
    ContactRequestCreateView,
    GuestListView,
    GuestUpgradeView,
    CenterAdminSubscriptionDetailView,
)
from .routers import api_router


urlpatterns = [
    # Router-registered viewsets (centers, groups, materials, mock-tests, assignments, attempts, notifications, etc.)
    path("", include(api_router.urls)),

    # Authentication endpoints
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/password/update/", UpdatePasswordView.as_view(), name="auth-password-update"),
    path(
        "auth/password/reset/",
        PasswordResetRequestView.as_view(),
        name="auth-password-reset-request",
    ),
    path(
        "auth/password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path(
        "auth/avatar/",
        UserAvatarUploadView.as_view(),
        name="auth-avatar-upload",
    ),

    # Analytics dashboards
    path(
        "analytics/owner/",
        OwnerAnalyticsView.as_view(),
        name="analytics-owner",
    ),
    path(
        "analytics/center-admin/",
        CenterAdminAnalyticsView.as_view(),
        name="analytics-center-admin",
    ),
    path(
        "analytics/teacher/",
        TeacherAnalyticsView.as_view(),
        name="analytics-teacher",
    ),
    path(
        "analytics/student/",
        StudentAnalyticsView.as_view(),
        name="analytics-student",
    ),

    # Centers / Invitations / Contact requests / Guests (standalone APIViews)
    path(
        "centers/invitations/",
        InvitationCreateView.as_view(),
        name="centers-invitation-create",
    ),
    path(
        "centers/invitations/list/",
        InvitationListView.as_view(),
        name="centers-invitation-list",
    ),
    path(
        "centers/invitations/approve/",
        InvitationApproveView.as_view(),
        name="centers-invitation-approve",
    ),
    path(
        "centers/create/",
        CenterCreateView.as_view(),
        name="centers-create",
    ),
    path(
        "centers/<uuid:center_id>/admins/create/",
        CenterAdminCreateView.as_view(),
        name="centers-admin-create",
    ),
    path(
        "centers/avatar/",
        CenterAvatarUploadView.as_view(),
        name="centers-avatar-upload",
    ),
    path(
        "contact-requests/",
        ContactRequestCreateView.as_view(),
        name="contact-requests-create",
    ),
    path(
        "guests/",
        GuestListView.as_view(),
        name="guests-list",
    ),
    path(
        "guests/upgrade/",
        GuestUpgradeView.as_view(),
        name="guests-upgrade",
    ),
    
    # Subscriptions
    path(
        "subscriptions/my-subscription/",
        CenterAdminSubscriptionDetailView.as_view(),
        name="my-subscription",
    ),
]

