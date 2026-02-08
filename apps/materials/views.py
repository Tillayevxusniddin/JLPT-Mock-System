# apps/materials/views.py
"""
Materials app API views. All OpenAPI schemas, multipart/form-data definitions,
MIME/extension rules, and visibility docs are in apps.materials.swagger; views
are thin and only apply decorators from that module.
"""
from django.db.models import Q
from rest_framework import viewsets, permissions, filters
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Material
from .serializers import MaterialSerializer
from .permissions import IsAdminOrTeacher, IsMaterialOwnerOrCenterAdmin
from .swagger import material_viewset_schema
from apps.groups.models import GroupMembership


@material_viewset_schema
class MaterialViewSet(viewsets.ModelViewSet):
    serializer_class = MaterialSerializer
    queryset = Material.objects.alive().order_by("-created_at")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["file_type", "is_public"]
    search_fields = ["name"]
    ordering_fields = ["created_at", "name"]
    ordering = ["-created_at"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        if self.action in ["update", "partial_update", "destroy"]:
            return [
                permissions.IsAuthenticated(),
                IsAdminOrTeacher(),
                IsMaterialOwnerOrCenterAdmin(),
            ]
        return [permissions.IsAuthenticated(), IsAdminOrTeacher()]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Material.objects.none()
        if not hasattr(self, 'request') or self.request is None:
            return Material.objects.none()

        user = self.request.user
        # SECURITY FIX: Use .alive() to filter soft-deleted materials
        base_qs = Material.objects.alive().order_by("-created_at")

        # CENTER_ADMIN, TEACHER: See all materials
        if user.role in ("CENTER_ADMIN", "TEACHER"):
            return base_qs

        # STUDENT: Can see public materials OR materials assigned to their groups
        if user.role == "STUDENT":
            return base_qs.filter(
                Q(is_public=True) | 
                Q(groups__memberships__user_id=user.id, groups__memberships__role_in_group=GroupMembership.ROLE_STUDENT)
            ).distinct()

        # GUEST: See nothing
        if user.role == "GUEST":
            return Material.objects.none()

        return Material.objects.none()

    def list(self, request, *args, **kwargs):
        # created_by is batch-fetched from public schema (user_map); see swagger MATERIALS_LIST_DESCRIPTION.
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        materials = page if page is not None else queryset
        
        # Optimize N+1 for created_by
        user_ids = set()
        for m in materials:
            if m.created_by_id:
                user_ids.add(m.created_by_id)
        
        user_map = {}
        if user_ids:
            from apps.core.tenant_utils import with_public_schema
            from apps.authentication.models import User
            
            def fetch_users():
                return {u.id: u for u in User.objects.filter(id__in=user_ids)}
            
            user_map = with_public_schema(fetch_users)
            
        serializer = self.get_serializer(
            materials, 
            many=True, 
            context={'request': request, 'user_map': user_map}
        )
        
        if page is not None:
            return self.get_paginated_response(serializer.data)
        
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(created_by_id=self.request.user.id)

    def perform_update(self, serializer):
        serializer.save()

