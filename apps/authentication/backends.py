#apps/authentication/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

class TenantAwareBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        
        center_id = None
        if request:
            center_id_header = request.headers.get("X-Organization-Id")
            if center_id_header:
                center_id = center_id_header

        try:
            if center_id:
                user = User.objects.get(email=username, center_id=center_id)
            else:
                user = User.objects.get(email=username, center__isnull=True)
            
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None