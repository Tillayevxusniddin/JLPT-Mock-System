import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

class Command(BaseCommand):
    help = 'Platforma egasini (Owner) yaratish'

    def handle(self, *args, **kwargs):
        email = os.environ.get('OWNER_EMAIL', 'admin@jlpt.uz')
        password = os.environ.get('OWNER_PASSWORD', 'admin123')
        
        if User.objects.filter(role=User.Role.OWNER).exists():
            self.stdout.write(self.style.WARNING(f"Diqqat: Owner allaqachon mavjud! ({email})"))
            return

        try:
            user = User.objects.create_superuser(
                email=email,
                password=password,
                first_name="Platform",
                last_name="Owner",
                role=User.Role.OWNER,
                organization=None,
                is_approved=True   
            )
            
            self.stdout.write(self.style.SUCCESS(f"Muvaffaqiyatli! Owner yaratildi.\nEmail: {email}\nParol: {password}"))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Xatolik yuz berdi: {str(e)}"))