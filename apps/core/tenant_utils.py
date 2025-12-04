import contextvars
from django.db import connection
from contextlib import contextmanager

# 1. Context Variable - Thread/Async safe storage
# Bu global o'zgaruvchi, lekin har bir request uchun alohida ishlaydi.
_current_schema = contextvars.ContextVar("current_schema", default="public")

def get_current_schema():
    """Joriy schemani qaytaradi"""
    return _current_schema.get()

def set_tenant_schema(schema_name):
    """
    PostgreSQL da search_path ni o'zgartiradi.
    Har doim 'public' ni oxiriga qo'shamiz, shunda umumiy jadvallar (User, Tenant) ko'rinib turadi.
    """
    # SQL Injection oldini olish uchun oddiy tekshiruv
    if not schema_name.isalnum() and "_" not in schema_name:
         raise ValueError(f"Invalid schema name: {schema_name}")

    with connection.cursor() as cursor:
        # search_path ni o'zgartirish
        # Masalan: SET search_path TO org_123, public
        cursor.execute(f"SET search_path TO {schema_name}, public")
        
    # Context dagi qiymatni yangilaymiz
    _current_schema.set(schema_name)

def set_public_schema():
    """Schemani public holatga qaytaradi"""
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")
    _current_schema.set("public")

@contextmanager
def schema_context(schema_name):
    """
    Context manager - vaqtinchalik schema o'zgartirish uchun.
    Foydalanish:
    with schema_context('org_test'):
        # bu yerdagi querylar org_test ichida bo'ladi
        pass
    # bu yerda yana eski holatiga qaytadi
    """
    previous_schema = get_current_schema()
    try:
        set_tenant_schema(schema_name)
        yield
    finally:
        # Ish tugagach, avvalgi schemani tiklaymiz
        if previous_schema == "public":
            set_public_schema()
        else:
            set_tenant_schema(previous_schema)