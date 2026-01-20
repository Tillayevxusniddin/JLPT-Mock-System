from celery import shared_task
from django.core.management import call_command
from apps.core.tenant_utils import set_tenant_schema, reset_tenant_schema
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def run_tenant_migrations(self, schema_name):
    """
    Run Django migrations for a tenant schema.
    """
    if not schema_name:
        logger.error("run_tenant_migrations called without schema_name")
        raise ValueError("schema_name is required")
    
    from django.db import connections
    from django.conf import settings
    from django.core.management.base import CommandError
    from apps.core.tenant_utils import schema_ready
    
    schema_was_set = False
    original_options = None
    
    try:
        # DB connection setup logic (same as before)
        original_options = connections['default'].settings_dict.get('OPTIONS', {}).copy()
        connections['default'].schema_name = schema_name
        connections['default'].settings_dict['OPTIONS'] = {
            **original_options,
            'options': f'-c search_path={schema_name},public'
        }
        
        if connections['default'].connection is not None:
            connections['default'].close()
        
        schema_was_set = True
        logger.info(f"🔧 Running migrations for schema: {schema_name}")
        
        # Create django_migrations table
        with connections['default'].cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS django_migrations (
                    id SERIAL PRIMARY KEY,
                    app VARCHAR(255) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    applied TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
            """)
        
        tenant_app_labels = _get_tenant_app_labels()
        
        if not tenant_app_labels:
            logger.warning(f"No tenant apps found to migrate for {schema_name}")
        else:
            logger.info(f"Migrating {len(tenant_app_labels)} tenant app(s): {', '.join(tenant_app_labels)}")
        
        migrated_count = 0
        for app_label in tenant_app_labels:
            try:
                call_command(
                    'migrate',
                    app_label,
                    database='default',
                    interactive=False,
                    verbosity=1,
                )
                migrated_count += 1
            except CommandError as e:
                # Filter out "no migrations" errors
                error_msg = str(e)
                if any(phrase in error_msg for phrase in [
                    'does not have migrations', 'No migrations to apply', 'has no migrations'
                ]):
                    continue
                else:
                    logger.warning(f"Migration warning for {app_label}: {e}")
        
        # Verification
        if not schema_ready(schema_name):
            raise Exception(f"Schema {schema_name} verified empty after migration.")
        
        # Update Center.is_ready status
        from apps.centers.models import Center
        try:
            reset_tenant_schema()
            center = Center.objects.get(schema_name=schema_name)
            center.is_ready = True
            center.save(update_fields=['is_ready'])
            logger.info(f"✅ Marked center '{center.name}' as ready")
        except Center.DoesNotExist:
            logger.error(f"❌ Center {schema_name} not found after migration")
            raise
        
        return f"Migrations completed for {schema_name}"
    
    except Exception as e:
        logger.error(f"❌ Failed to run migrations: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
    
    finally:
        if schema_was_set:
            if original_options is not None:
                connections['default'].settings_dict['OPTIONS'] = original_options
            connections['default'].schema_name = 'public'
            reset_tenant_schema()
            if connections['default'].connection is not None:
                connections['default'].close()

def _get_tenant_app_labels():
    """Extract app labels from TENANT_APPS that have migrations."""
    from django.apps import apps
    from django.db.migrations.loader import MigrationLoader
    from django.db import connection
    from django.conf import settings
    
    app_labels = []
    loader = MigrationLoader(connection)
    
    for app_name in settings.TENANT_APPS:
        if '.' in app_name:
            app_label = app_name.split('.')[-1]
        else:
            app_label = app_name
        
        if app_label in ['rest_framework', 'django_filters', 'drf_spectacular', 'channels', 'corsheaders', 'axes', 'storages']:
            continue
            
        if app_name.startswith('django.contrib.') and app_label not in ['auth', 'contenttypes', 'admin', 'sessions']:
            continue
        
        try:
            apps.get_app_config(app_label)
            if loader.migrated_apps and app_label not in loader.migrated_apps:
                continue
        except LookupError:
            continue
        
        if app_label not in app_labels:
            app_labels.append(app_label)
    return app_labels

@shared_task
def cleanup_failed_schemas():
    """Cleanup task to find and fix schemas with missing tables."""
    from apps.centers.models import Center
    from apps.core.tenant_utils import schema_context
    from django.db import connection
    
    results = {'checked': 0, 'repaired': 0, 'failed': 0}
    active_centers = Center.objects.filter(is_active=True, deleted_at__isnull=True)
    
    for center in active_centers:
        if not center.schema_name: continue
        results['checked'] += 1
        try:
            with schema_context(center.schema_name):
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT COUNT(*) FROM information_schema.tables
                        WHERE table_schema = %s AND table_type = 'BASE TABLE'
                    """, [center.schema_name])
                    if cursor.fetchone()[0] == 0:
                        run_tenant_migrations.delay(center.schema_name)
                        results['repaired'] += 1
        except Exception:
            results['failed'] += 1
    return results

@shared_task(bind=True, max_retries=3)
def hard_delete_center(self, center_id):
    """
    HARD DELETE center - Center va unga tegishli BARCHA narsani o'chirib tashlash.
    
    Bajariladigan ishlar:
    1. Centerga tegishli barcha Userlarni o'chiradi (Public User tabledan).
    2. Tenant Schema (bazadagi alohida schema) ni DROP qiladi.
    3. Centerga tegishli S3 dagi avatarlarni o'chiradi.
    4. Center jadvalining o'zini o'chiradi.
    
    DIQQAT: Bu jarayonni orqaga qaytarib bo'lmaydi!
    """
    from apps.centers.models import Center
    from apps.authentication.models import User # Authentication appdan olish
    from django.db import connection
    import time
    
    start_time = time.time()
    
    try:
        # Centerni olish (agar soft delete bo'lsa ham topish uchun all_objects)
        try:
            center = Center.all_objects.get(id=center_id)
        except Center.DoesNotExist:
            return f"Center {center_id} not found"
        
        schema_name = center.schema_name
        logger.info(f"🗑️  Starting HARD DELETE for center {center_id} ({center.name})")
        
        # ---------------------------------------------------------
        # 1-QADAM: Userlarni o'chirish (Hard Delete)
        # ---------------------------------------------------------
        # Biz userlarni ORM orqali o'chirishga harakat qilamiz, lekin 
        # schema o'chirilishi bilan bog'liq xatoliklar bo'lsa, RAW SQL ishlatamiz.
        users = User.all_objects.filter(center_id=center_id)
        deleted_users_count = 0
        
        for user in users.iterator(chunk_size=100):
            try:
                # Avatarni o'chirish
                if user.avatar:
                    try: user.avatar.delete(save=False)
                    except: pass
                
                user_email = user.email
                try:
                    # Userni o'chirish
                    user.hard_delete() 
                    deleted_users_count += 1
                except Exception:
                    # Agar ORM xato bersa (masalan, tenant tablega bog'liqlik bo'lsa)
                    # To'g'ridan-to'g'ri SQL bilan o'chiramiz
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute("DELETE FROM authentication_user WHERE id = %s", [str(user.id)])
                        deleted_users_count += 1
                    except Exception as e:
                        logger.error(f"Failed to delete user {user_email}: {e}")
                        
            except Exception as e:
                logger.error(f"Error processing user {user.id}: {e}")

        # ---------------------------------------------------------
        # 2-QADAM: Public Schema ma'lumotlarini tozalash
        # ---------------------------------------------------------
        try:
            with connection.cursor() as cursor:
                # Invitations
                cursor.execute("DELETE FROM centers_invitation WHERE center_id = %s", [center_id])
                # Contact Requests
                cursor.execute("DELETE FROM centers_contactrequest WHERE center_name = %s", [center.name])
                # Subscriptions
                cursor.execute("DELETE FROM subscriptions WHERE center_id = %s", [center_id])
        except Exception as e:
            logger.warning(f"Error cleaning related public data: {e}")

        # ---------------------------------------------------------
        # 3-QADAM: Tenant Schemani DROP qilish
        # ---------------------------------------------------------
        if schema_name:
            try:
                with connection.cursor() as cursor:
                    # Schema borligini tekshirish
                    cursor.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", [schema_name])
                    if cursor.fetchone():
                        # CASCADE - ichidagi barcha jadvallar bilan qo'shib o'chiradi
                        cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
                        logger.info(f"✅ Schema {schema_name} dropped")
            except Exception as e:
                logger.error(f"Failed to drop schema {schema_name}: {e}")

        # ---------------------------------------------------------
        # 4-QADAM: Center obyektini o'chirish
        # ---------------------------------------------------------
        if center.avatar:
            try: center.avatar.delete(save=False)
            except: pass
            
        center.hard_delete() # Bazadan butunlay o'chirish
        
        elapsed_time = time.time() - start_time
        logger.info(f"🎉 Center {center.name} deleted completely in {elapsed_time:.2f}s")
        
        return {
            "status": "deleted",
            "center_name": center.name,
            "users_deleted": deleted_users_count
        }
    
    except Exception as e:
        logger.error(f"❌ HARD DELETE FAILED: {str(e)}", exc_info=True)
        # 5 minutdan keyin qayta urinib ko'rish
        raise self.retry(exc=e, countdown=300)