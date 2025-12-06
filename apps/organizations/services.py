import logging
from django.db import connection, transaction
from django.core.management import call_command
from apps.core.tenant_utils import schema_context

try:
    from psycopg2 import sql
except ImportError:
    sql = None

logger = logging.getLogger(__name__)

def create_organization_schema(schema_name):
    """
    Create PostgreSQL schema for new tenant and run migrations.
    Uses transaction to ensure atomicity - if migration fails, schema is rolled back.
    
    Args:
        schema_name: Name of the schema to create (e.g., 'tenant_cambridge')
    
    Returns:
        bool: True if successful, False if failed
    """
    try:
        with transaction.atomic():
            # 1. Create schema
            with connection.cursor() as cursor:
                if sql:
                    cursor.execute(
                        sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                            sql.Identifier(schema_name)
                        )
                    )
                else:
                    # Fallback for testing
                    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
                
                logger.info(f"Schema created: {schema_name}")

            # 2. Apply migrations within the new schema
            with schema_context(schema_name):
                logger.info(f"Applying migrations for {schema_name}...")
                call_command('migrate', interactive=False, verbosity=0)
                logger.info(f"Migrations applied successfully for {schema_name}")
            
            return True
            
    except Exception as e:
        logger.error(f"CRITICAL: Failed to create schema {schema_name}: {e}")
        
        # Cleanup: Attempt to drop the incomplete schema
        try:
            with connection.cursor() as cursor:
                if sql:
                    cursor.execute(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                            sql.Identifier(schema_name)
                        )
                    )
                else:
                    cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
                
                logger.info(f"Rolled back incomplete schema: {schema_name}")
        except Exception as cleanup_error:
            logger.critical(
                f"FAILED TO ROLLBACK schema {schema_name}: {cleanup_error}. "
                f"Manual cleanup required!"
            )
        
        # Mark organization as needing setup
        try:
            from apps.organizations.models import Organization
            Organization.objects.filter(schema_name=schema_name).update(
                status='SUSPENDED'
            )
            logger.warning(f"Organization with schema {schema_name} marked as SUSPENDED")
        except Exception as update_error:
            logger.error(f"Failed to update organization status: {update_error}")
        
        return False

def delete_organization_schema(schema_name):
    """
    Delete organization schema. USE WITH EXTREME CAUTION!
    In production, consider renaming to 'archived_*' instead of deleting.
    
    Args:
        schema_name: Name of the schema to delete
    
    Returns:
        bool: True if successful, False if failed
    """
    # Safety check: Don't delete public schema or system schemas
    if schema_name in ['public', 'information_schema', 'pg_catalog']:
        logger.error(f"Attempted to delete protected schema: {schema_name}")
        return False
    
    try:
        with connection.cursor() as cursor:
            if sql:
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema_name)
                    )
                )
            else:
                cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
            
            logger.warning(f"Schema deleted: {schema_name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete schema {schema_name}: {e}")
        return False