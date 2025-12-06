from django.urls import path
from .views import (
    InvitationListView,
    InvitationCreateView,
    InvitationDetailView,
    InvitationUpdateView,
    CheckInvitationView
)

urlpatterns = [
    path('', InvitationListView.as_view(), name='list-invitations'),
    path('create/', InvitationCreateView.as_view(), name='create-invitation'),
    path('check/', CheckInvitationView.as_view(), name='check-invitation'),
    path('<int:pk>/', InvitationDetailView.as_view(), name='invitation-detail'),
    path('<int:pk>/update/', InvitationUpdateView.as_view(), name='invitation-update'),
]