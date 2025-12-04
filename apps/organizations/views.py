from rest_framework import generics, permissions
from .models import Organization
from .serializers import OrganizationSerializer # Buni pastda yaratamiz

class OrganizationCreateView(generics.CreateAPIView):
    """
    Faqat OWNER yangi tashkilot (Tenant) yarata oladi.
    """
    queryset = Organization.objects.all()
    # IsOwner permission hali yozilmagan bo'lsa, vaqtincha IsAuthenticated yoki IsAdminUser turibdi
    permission_classes = [permissions.IsAdminUser] 
    serializer_class = OrganizationSerializer