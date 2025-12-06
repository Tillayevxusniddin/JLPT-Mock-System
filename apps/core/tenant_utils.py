import re
import contextvars
from django.db import connection
from contextlib import contextmanager

try:
    from psycopg2 import sql
except ImportError:
    # Fallback for non-PostgreSQL databases (testing with SQLite)
    sql = None


SCHEMA_NAME_REGEX = re.compile(r'^[a-z0-9_]+$')
MAX_SCHEMA_NAME_LENGTH = 63  # PostgreSQL identifier limit

_current_schema = contextvars.ContextVar("current_schema", default="public")

def get_current_schema():
    """Get the current schema name from context"""
    return _current_schema.get()

def set_tenant_schema(schema_name):
    """
    Set PostgreSQL search_path to tenant schema.
    Uses psycopg2.sql.Identifier for SQL injection protection.
    """
    # Strict validation
    if not SCHEMA_NAME_REGEX.match(schema_name):
        raise ValueError(f"Invalid schema name: {schema_name}")
    
    # PostgreSQL identifier length limit
    if len(schema_name) > MAX_SCHEMA_NAME_LENGTH:
        raise ValueError(f"Schema name too long (max {MAX_SCHEMA_NAME_LENGTH}): {schema_name}")

    with connection.cursor() as cursor:
        if sql:
            # Use psycopg2.sql.Identifier for safe schema name handling
            cursor.execute(
                sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(schema_name)
                )
            )
        else:
            # Fallback for testing (already validated by regex)
            cursor.execute(f"SET search_path TO {schema_name}, public")
    
    _current_schema.set(schema_name)

def set_public_schema():
    """Reset PostgreSQL search_path to public schema"""
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")
    _current_schema.set("public")

def reset_tenant_schema():
    """
    Alias for set_public_schema().
    Resets the database connection to the public schema.
    """
    set_public_schema()

def schema_exists(schema_name):
    """
    Check if a schema exists in the database.
    Returns True if exists, False otherwise.
    """
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