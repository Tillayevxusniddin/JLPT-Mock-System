"""
Management command to migrate all tenant schemas

Usage:
    python manage.py migrate_tenants
    python manage.py migrate_tenants --schema tenant_abc123
    python manage.py migrate_tenants --skip-public

This command must be run after any model changes to ensure all tenant
schemas are up to date with the latest migrations.
"""
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import connection, connections
from django.conf import settings
import logging

from apps.organizations.models import Organization
from apps.core.tenant_utils import set_tenant_schema, reset_tenant_schema, schema_exists

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run migrations on all tenant schemas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema',
            type=str,
            help='Migrate only this specific schema (e.g., tenant_abc123)'
        )
        parser.add_argument(
            '--skip-public',
            action='store_true',
            help='Skip migrating the public schema (only migrate tenants)'
        )
        parser.add_argument(
            '--fake',
            action='store_true',
            help='Mark migrations as run without actually running them'
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all tenant schemas without running migrations'
        )

    def handle(self, *args, **options):
        """Execute the migrate_tenants command"""
        
        # List mode - just show all schemas
        if options['list']:
            self.list_tenant_schemas()
            return

        # Step 1: Migrate public schema (unless --skip-public)
        if not options['skip_public']:
            self.stdout.write(self.style.MIGRATE_HEADING('\n=== Migrating PUBLIC schema ==='))
            try:
                reset_tenant_schema()
                call_command(
                    'migrate',
                    database=settings.TENANT_DB_ALIAS,
                    verbosity=1,
                    fake=options['fake']
                )
                self.stdout.write(self.style.SUCCESS('✓ Public schema migrated successfully'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Failed to migrate public schema: {e}'))
                raise CommandError(f'Public schema migration failed: {e}')

        # Step 2: Migrate tenant schemas
        if options['schema']:
            # Migrate single schema
            self.migrate_single_schema(options['schema'], options['fake'])
        else:
            # Migrate all tenant schemas
            self.migrate_all_schemas(options['fake'])

        self.stdout.write(self.style.SUCCESS('\n✓ All migrations completed successfully!'))

    def list_tenant_schemas(self):
        """List all tenant schemas in the database"""
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Tenant Schemas ===\n'))
        
        tenant_schemas = self.get_all_tenant_schemas()
        
        if not tenant_schemas:
            self.stdout.write(self.style.WARNING('No tenant schemas found.'))
            return
        
        # Get organization info for each schema
        organizations = Organization.objects.all().values('schema_name', 'name', 'status')
        org_map = {org['schema_name']: org for org in organizations}
        
        self.stdout.write(self.style.MIGRATE_LABEL(f'Found {len(tenant_schemas)} tenant schema(s):\n'))
        
        for i, schema in enumerate(tenant_schemas, 1):
            org_info = org_map.get(schema)
            if org_info:
                status_color = self.style.SUCCESS if org_info['status'] == 'ACTIVE' else self.style.WARNING
                self.stdout.write(
                    f"{i}. {schema} → {org_info['name']} "
                    f"[{status_color(org_info['status'])}]"
                )
            else:
                self.stdout.write(
                    f"{i}. {schema} "
                    f"[{self.style.ERROR('ORPHANED - No organization found')}]"
                )
        
        self.stdout.write('')

    def get_all_tenant_schemas(self):
        """Query database for all tenant schemas"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name LIKE 'tenant_%'
                ORDER BY schema_name
            """)
            return [row[0] for row in cursor.fetchall()]

    def migrate_single_schema(self, schema_name, fake=False):
        """Migrate a single tenant schema"""
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n=== Migrating schema: {schema_name} ==='))
        
        # Validate schema exists
        if not schema_exists(schema_name):
            raise CommandError(f'Schema "{schema_name}" does not exist')
        
        try:
            # Switch to tenant schema
            set_tenant_schema(schema_name)
            
            # Get organization info
            org = Organization.objects.filter(schema_name=schema_name).first()
            if org:
                self.stdout.write(f'Organization: {org.name} (Status: {org.status})')
            
            # Run migrations
            self.stdout.write('Running migrations...')
            call_command(
                'migrate',
                database=settings.TENANT_DB_ALIAS,
                verbosity=1,
                fake=fake
            )
            
            self.stdout.write(self.style.SUCCESS(f'✓ Schema {schema_name} migrated successfully'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Failed to migrate {schema_name}: {e}'))
            logger.error(f'Migration failed for {schema_name}: {e}', exc_info=True)
            raise CommandError(f'Migration failed for {schema_name}: {e}')
        
        finally:
            # Always reset to public schema
            reset_tenant_schema()

    def migrate_all_schemas(self, fake=False):
        """Migrate all tenant schemas"""
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Migrating ALL tenant schemas ===\n'))
        
        tenant_schemas = self.get_all_tenant_schemas()
        
        if not tenant_schemas:
            self.stdout.write(self.style.WARNING('No tenant schemas found. Nothing to migrate.'))
            return
        
        total = len(tenant_schemas)
        success_count = 0
        failed_schemas = []
        
        self.stdout.write(self.style.MIGRATE_LABEL(f'Found {total} tenant schema(s) to migrate\n'))
        
        for i, schema_name in enumerate(tenant_schemas, 1):
            self.stdout.write(self.style.MIGRATE_HEADING(f'\n[{i}/{total}] Migrating: {schema_name}'))
            
            try:
                # Switch to tenant schema
                set_tenant_schema(schema_name)
                
                # Get organization info
                org = Organization.objects.filter(schema_name=schema_name).first()
                if org:
                    self.stdout.write(f'    Organization: {org.name} (Status: {org.status})')
                else:
                    self.stdout.write(self.style.WARNING(f'    ⚠ ORPHANED - No organization found'))
                
                # Run migrations
                self.stdout.write('    Running migrations...')
                call_command(
                    'migrate',
                    database=settings.TENANT_DB_ALIAS,
                    verbosity=0,  # Reduce verbosity for batch operations
                    fake=fake,
                    interactive=False
                )
                
                self.stdout.write(self.style.SUCCESS(f'    ✓ Success'))
                success_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'    ✗ Failed: {e}'))
                logger.error(f'Migration failed for {schema_name}: {e}', exc_info=True)
                failed_schemas.append((schema_name, str(e)))
            
            finally:
                # Always reset to public schema
                reset_tenant_schema()
        
        # Summary
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Migration Summary ==='))
        self.stdout.write(self.style.SUCCESS(f'✓ Successful: {success_count}/{total}'))
        
        if failed_schemas:
            self.stdout.write(self.style.ERROR(f'✗ Failed: {len(failed_schemas)}/{total}\n'))
            self.stdout.write(self.style.ERROR('Failed schemas:'))
            for schema_name, error in failed_schemas:
                self.stdout.write(f'  - {schema_name}: {error}')
            raise CommandError(f'{len(failed_schemas)} schema(s) failed to migrate')
