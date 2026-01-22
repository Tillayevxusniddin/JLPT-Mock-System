#apps/core/tenant_utils.py
import re
import contextvars
from django.db import connection
from contextlib import contextmanager
from asgiref.sync import sync_to_async

try: 
    from psycopg2 import sql
except ImportError:
    sql = None

SCHEMA_NAME_REGEX = re.compile(r'^[a-z0-9_]+$')
MAX_SCHEMA_NAME_LENGTH = 63

_current_schema = contextvars.ContextVar("current_schema", default="public")

def get_current_schema():
    return _current_schema.get()

def set_tenant_schema(schema_name):
    if not SCHEMA_NAME_REGEX.match(schema_name): raise ValueError(f"Invalid schema name: {schema_name}")
    if len(schema_name) > MAX_SCHEMA_NAME_LENGTH: raise ValueError(f"Schema name too long (max {MAX_SCHEMA_NAME_LENGTH}): {schema_name}")

    with connection.cursor() as cursor:
        if sql:
            cursor.execute( 
                sql.SQL("SET search_path TO {}, public").format(
                     sql.Identifier(schema_name) 
                ) 
            )
        else: 
            cursor.execute(f"SET search_path TO {schema_name}, public")
        
    _current_schema.set(schema_name)
            
def set_public_schema(): 
    with connection.cursor() as cursor: 
        cursor.execute("SET search_path TO public") 
    _current_schema.set("public")

def reset_tenant_schema():
    set_public_schema()

def schema_exists(schema_name):
    if not SCHEMA_NAME_REGEX.match(schema_name):
        return False
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.schemata 
                WHERE schema_name = %s
            )
        """, [schema_name])
        return cursor.fetchone()[0]

def schema_ready(schema_name, table_name="groups_group"): #for example groups_group table
    if not schema_exists(schema_name): return False

    try:
        with connection.cursor() as cursor:
            cursor.execute(""" 
                SELECT EXISTS ( 
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_schema = %s AND table_name = %s 
                ) 
            """, [schema_name, table_name])
            return cursor.fetchone()[0]
    except Exception as e:
        return False

@contextmanager
def schema_context(schema_name):
    previous_schema = get_current_schema()
    try:
        set_tenant_schema(schema_name)
        yield
    finally:
        if previous_schema == "public":
            set_public_schema()
        else:
            set_tenant_schema(previous_schema)

def with_public_schema(func):
    previous_schema = get_current_schema()
    try:
        set_public_schema()
        return func()
    finally:
        if previous_schema == "public":
            set_public_schema()
        else:
            set_tenant_schema(previous_schema)

def get_public_user_by_id(user_id):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    previous_schema = get_current_schema()
    try:
        set_public_schema()
        return User.objects.filter(id=user_id).first()
    except Exception:
        return None
    finally:
        if previous_schema == "public":
            set_public_schema()
        else:
            set_tenant_schema(previous_schema)

# =============================================================================
# ASYNC-SAFE SCHEMA SWITCHING FUNCTIONS FOR DJANGO CHANNELS
# =============================================================================

async def set_tenant_schema_async(schema_name):
    await sync_to_async(set_tenant_schema)(schema_name)

async def set_public_schema_async():
    await sync_to_async(set_public_schema)()

async def reset_tenant_schema_async():
    await sync_to_async(reset_tenant_schema)()

async def schema_exists_async(schema_name):
    return await sync_to_async(schema_exists)(schema_name)

async def schema_ready_async(schema_name):
    return await sync_to_async(schema_ready)(schema_name, table_name="groups_group")

