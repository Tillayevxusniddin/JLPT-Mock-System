#apps/authentication/signals.py
from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.dispatch import receiver
from .models import User, UserActivity

@receiver(user_logged_in)
@transaction.atomic
def log_user_login(sender, request, user: User, **kwargs):
    try:
        ip = request.META.get("REMOTE_ADDR") if request else None #TODO: Ba’zan reverse proxy bo‘lsa, HTTP_X_FORWARDED_FOR ishlatiladi (bu joyni keyin yaxshilash mumkin).
        agent = request.META.get("HTTP_USER_AGENT", "") if request else ""
        user.update_last_login_info(ip=ip, agent=agent)
        UserActivity.objects.create(user=user, ip_address=ip, user_agent=agent)
    except Exception:
        pass






