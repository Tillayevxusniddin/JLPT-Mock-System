from django.urls import path
from .views import InvitationCreateView, CheckInvitationView

urlpatterns = [
    path('create/', InvitationCreateView.as_view(), name='create-invitation'),
    path('check/', CheckInvitationView.as_view(), name='check-invitation'),
]