from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GroupViewSet

router = DefaultRouter()
router.register(r'', GroupViewSet, basename='groups')

urlpatterns = [
    path('', include(router.urls)),
]