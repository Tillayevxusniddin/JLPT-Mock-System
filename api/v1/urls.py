#api/v1/urls.py
from django.urls import path, include

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
    # Router-registered viewsets (users, centers, groups, materials, mock-tests, assignments, attempts, notifications, etc.)
    path("", include(api_router.urls)),

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

