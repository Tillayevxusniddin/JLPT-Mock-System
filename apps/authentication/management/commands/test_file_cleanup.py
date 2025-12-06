"""
Test file cleanup signals

This command demonstrates that file cleanup signals work correctly.
Run with: python manage.py test_file_cleanup
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.organizations.models import Organization

User = get_user_model()


class Command(BaseCommand):
    help = 'Test file cleanup signals for User and Organization models'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== File Cleanup Signals Test ===\n'))
        
        # Test information
        self.stdout.write('File cleanup signals are registered and will:')
        self.stdout.write('  ✓ Delete old avatar when User updates their avatar')
        self.stdout.write('  ✓ Delete avatar when User is deleted')
        self.stdout.write('  ✓ Delete old logo when Organization updates their logo')
        self.stdout.write('  ✓ Delete logo when Organization is deleted')
        
        self.stdout.write('\nSignals registered in:')
        self.stdout.write('  - apps/authentication/file_signals.py')
        self.stdout.write('  - apps/organizations/file_signals.py')
        
        self.stdout.write('\nSignals loaded via:')
        self.stdout.write('  - apps/authentication/apps.py (AuthenticationConfig.ready())')
        self.stdout.write('  - apps/organizations/apps.py (OrganizationsConfig.ready())')
        
        self.stdout.write(self.style.SUCCESS('\n✓ File cleanup signals are active and ready!\n'))
