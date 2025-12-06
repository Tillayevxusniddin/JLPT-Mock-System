from django.urls import path
from .views import (
    OrganizationListView,
    OrganizationDetailView,
    OrganizationUpdateView,
    OrganizationCreateView
)

urlpatterns = [
    path('', OrganizationListView.as_view(), name='organization-list'),
    path('create/', OrganizationCreateView.as_view(), name='organization-create'),
    path('<int:pk>/', OrganizationDetailView.as_view(), name='organization-detail'),
    path('<int:pk>/update/', OrganizationUpdateView.as_view(), name='organization-update'),
]