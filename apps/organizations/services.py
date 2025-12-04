import logging
from django.db import connection
from django.core.management import call_command
from apps.core.tenant_utils import schema_context

logger = logging.getLogger(__name__)

def create_organization_schema(schema_name):
    """
    Yangi tenant uchun PostgreSQL schema yaratadi va jadvallarni migratsiya qiladi.
    """
    try:
        # 1. Schema yaratish
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
            logger.info(f"Schema created: {schema_name}")

        # 2. Migratsiyalarni shu schema ichida ishga tushirish
        # Bu context manager 'search_path' ni o'zgartiradi
        with schema_context(schema_name):
            logger.info(f"Applying migrations for {schema_name}...")
            
            # DIQQAT: Bu yerda 'interactive=False' bo'lishi shart.
            call_command('migrate', interactive=False)
            
        return True
    except Exception as e:
        logger.error(f"Error creating schema {schema_name}: {e}")
        return False

def delete_organization_schema(schema_name):
    """
    Ehtiyot bo'lish kerak! Ma'lumotlar o'chib ketadi.
    Odatda productionda schema o'chirilmaydi, faqat "archived_org_xyz" deb rename qilinadi.
    """
    # Xavfsizlik uchun hozircha o'chirib qo'yamiz
    pass