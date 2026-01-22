#apps/core/management/commands/migrate_tenants.py
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import connection, connections
from django.conf import settings
from django.apps import apps
import logging
from contextlib import contextmanager

# Local imports
from apps.core.tenant_utils import schema_exists, reset_tenant_schema

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run migrations on all tenant schemas'

    def add_arguments(self, parser):
        parser.add_argument('--schema', type=str, help='Migrate only this specific schema')
        parser.add_argument('--skip-public', action='store_true', help='Skip migrating the public schema')
        parser.add_argument('--fake', action='store_true', help='Mark migrations as run without actually running them')
        parser.add_argument('--list', action='store_true', help='List all tenant schemas without running migrations')

    @contextmanager
    def schema_context(self, schema_name):
        """
        Context manager to force a connection to use a specific schema.
        This modifies the DB connection OPTIONS to set search_path at the driver level.
        """
        original_options = connections['default'].settings_dict.get('OPTIONS', {}).copy()
        original_schema_name = getattr(connections['default'], 'schema_name', 'public')

        try:
            # 1. Router uchun schema nomini belgilaymiz
            connections['default'].schema_name = schema_name
            
            # 2. Driver darajasida search_path ni o'zgartiramiz
            connections['default'].settings_dict['OPTIONS'] = {
                **original_options,
                'options': f'-c search_path={schema_name},public'
            }
            
            # 3. Eski connectionni yopamiz (yangi options bilan qayta ochilishi uchun)
            if connections['default'].connection is not None:
                connections['default'].close()
            
            yield
            
        finally:
            # Cleanup: Hammasini joyiga qaytaramiz
            connections['default'].settings_dict['OPTIONS'] = original_options
            connections['default'].schema_name = original_schema_name
            
            if connections['default'].connection is not None:
                connections['default'].close()

    def handle(self, *args, **options):
        
        if options['list']:
            self.list_tenant_schemas()
            return

        # =================================================
        # STEP 1: PUBLIC SCHEMA MIGRATION
        # =================================================
        if not options['skip_public']:
            self.stdout.write(self.style.MIGRATE_HEADING('\n=== Migrating PUBLIC schema ==='))
            try:
                # Reset to ensure we are purely on public
                reset_tenant_schema()
                
                # Filter apps explicitly allowed for Public
                shared_app_labels = self._get_app_labels(settings.SHARED_APPS)
                
                for app_label in shared_app_labels:
                    self._run_migration(app_label, fake=options['fake'])
                
                self.stdout.write(self.style.SUCCESS('✓ Public schema migrated successfully'))
            except Exception as e:
                raise CommandError(f'Public schema migration failed: {e}')

        # =================================================
        # STEP 2: TENANT SCHEMAS MIGRATION
        # =================================================
        if options['schema']:
            self.migrate_single_schema(options['schema'], options['fake'])
        else:
            self.migrate_all_schemas(options['fake'])

        self.stdout.write(self.style.SUCCESS('\n✓ All migrations completed successfully!'))

    def list_tenant_schemas(self):
        """List schemas safely"""
        schemas = self.get_all_tenant_schemas()
        self.stdout.write(f"Found {len(schemas)} schemas: {', '.join(schemas)}")

    def get_all_tenant_schemas(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'center_%'")
            return [row[0] for row in cursor.fetchall()]

    def migrate_single_schema(self, schema_name, fake=False):
        if not schema_exists(schema_name):
            raise CommandError(f'Schema "{schema_name}" does not exist')

        self.stdout.write(self.style.MIGRATE_HEADING(f'\n=== Migrating schema: {schema_name} ==='))
        
        with self.schema_context(schema_name):
            self._ensure_migration_table()
            self._run_tenant_migrations(fake)
            self.stdout.write(self.style.SUCCESS(f'✓ Schema {schema_name} migrated successfully'))

    def migrate_all_schemas(self, fake=False):
        schemas = self.get_all_tenant_schemas()
        if not schemas:
            self.stdout.write(self.style.WARNING('No tenant schemas found.'))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(f'\n=== Migrating {len(schemas)} tenant schemas ==='))
        
        failed = []
        for i, schema in enumerate(schemas, 1):
            self.stdout.write(f"[{i}/{len(schemas)}] Processing {schema}...")
            
            # Optional: Center info (Safe lookup)
            try:
                from apps.centers.models import Center
                center = Center.objects.filter(schema_name=schema).first()
                if center:
                    self.stdout.write(f"   Center: {center.name}")
            except Exception:
                pass # Center table bo'lmasa yoki xatolik bo'lsa, ignor qilamiz
            
            try:
                with self.schema_context(schema):
                    self._ensure_migration_table()
                    self._run_tenant_migrations(fake)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ✗ Failed: {e}"))
                failed.append((schema, str(e)))

        if failed:
            self.stdout.write(self.style.ERROR(f"\nFailed schemas ({len(failed)}):"))
            for s, e in failed:
                self.stdout.write(f" - {s}: {e}")
            raise CommandError("Some schemas failed to migrate.")

    def _ensure_migration_table(self):
        """Creates django_migrations table if not exists"""
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS django_migrations (
                    id SERIAL PRIMARY KEY,
                    app VARCHAR(255) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    applied TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
            """)

    def _run_tenant_migrations(self, fake):
        tenant_apps = self._get_app_labels(settings.TENANT_APPS)
        for app in tenant_apps:
            self._run_migration(app, fake=fake, verbosity=0)

    def _run_migration(self, app_label, fake=False, verbosity=1):
        try:
            call_command(
                'migrate',
                app_label,
                database='default',
                verbosity=verbosity,
                fake=fake,
                interactive=False
            )
        except Exception as e:
            # Skip "No migrations" errors gracefully
            if 'does not have migrations' in str(e) or 'No migrations' in str(e):
                return
            self.stdout.write(self.style.WARNING(f"   ⚠ Warning in {app_label}: {e}"))

    def _get_app_labels(self, app_list):
        """Extracts label from apps.xxx and checks if it's valid"""
        valid_labels = []
        
        # Bu ro'yxatdan 'axes' ni olib tashladim, chunki u migratsiyaga muhtoj!
        ignore_apps = [
            'rest_framework', 'django_filters', 'drf_spectacular', 
            'channels', 'corsheaders', 'storages'
        ]
        
        for app_conf in app_list:
            label = app_conf.split('.')[-1]
            if label in ignore_apps:
                continue
            
            try:
                # Check if app is installed
                apps.get_app_config(label)
                valid_labels.append(label)
            except LookupError:
                continue
                
        # Remove duplicates
        return list(dict.fromkeys(valid_labels))