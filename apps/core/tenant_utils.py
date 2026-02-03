# apps/core/tenant_utils.py
"""
PostgreSQL schema utilities for shared-DB, separate-schema multi-tenancy.

- Context is tracked via contextvars so it is thread- and async-context safe
  within a single request/task. With CONN_MAX_AGE > 0, always set search_path
  at request start (TenantMiddleware) and end so pooled connections are safe.
- For WebSocket consumers: use run_in_tenant_schema_async(schema_name, sync_func)
  so DB work runs on the same connection that had search_path set (per-message
  isolation).
"""
import logging
import re
import contextvars
from contextlib import contextmanager

from asgiref.sync import sync_to_async
from django.db import connection

logger = logging.getLogger(__name__)

try:
    from psycopg2 import sql
except ImportError:
    sql = None

SCHEMA_NAME_REGEX = re.compile(r"^[a-z0-9_]+$")
MAX_SCHEMA_NAME_LENGTH = 63
RESERVED_SCHEMAS = frozenset({"public", "information_schema", "pg_catalog", "pg_toast"})

_current_schema = contextvars.ContextVar("current_schema", default="public")


def get_current_schema():
    """Return the current schema name from context (default 'public')."""
    return _current_schema.get()


def _validate_schema_name(schema_name):
    if not schema_name or not isinstance(schema_name, str):
        raise ValueError("Schema name must be a non-empty string")
    if schema_name in RESERVED_SCHEMAS and schema_name != "public":
        raise ValueError(f"Reserved schema name: {schema_name}")
    if schema_name != "public" and not SCHEMA_NAME_REGEX.match(schema_name):
        raise ValueError(f"Invalid schema name: {schema_name}")
    if len(schema_name) > MAX_SCHEMA_NAME_LENGTH:
        raise ValueError(
            f"Schema name too long (max {MAX_SCHEMA_NAME_LENGTH}): {schema_name}"
        )


def set_tenant_schema(schema_name):
    """Set the connection search_path and context to the given tenant schema."""
    _validate_schema_name(schema_name)
    with connection.cursor() as cursor:
        if sql:
            cursor.execute(
                sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(schema_name)
                )
            )
        else:
            cursor.execute("SET search_path TO %s, public", [schema_name])
    _current_schema.set(schema_name)


def set_public_schema():
    """Reset search_path to public. Always syncs _current_schema even on failure."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
    finally:
        _current_schema.set("public")

def reset_tenant_schema():
    set_public_schema()

def schema_exists(schema_name):
    if not schema_name or not SCHEMA_NAME_REGEX.match(schema_name):
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS(
                SELECT 1 FROM information_schema.schemata
                WHERE schema_name = %s
            )
            """,
            [schema_name],
        )
        return cursor.fetchone()[0]


def schema_ready(schema_name, table_name="groups_group"):
    """Return True if the schema exists and contains the given table."""
    if not schema_exists(schema_name):
        return False
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                )
                """,
                [schema_name, table_name],
            )
            return cursor.fetchone()[0]
    except Exception:
        return False


@contextmanager
def schema_context(schema_name):
    """
    Execute a block with search_path set to the given tenant schema, then restore.
    Safe for nested use; restores the previous schema (public or tenant) on exit.
    """
    previous_schema = get_current_schema()
    try:
        set_tenant_schema(schema_name)
        yield
    finally:
        if previous_schema == "public":
            set_public_schema()
        else:
            try:
                set_tenant_schema(previous_schema)
            except Exception as e:
                logger.warning(
                    "schema_context: failed to restore tenant %s, resetting to public: %s",
                    previous_schema,
                    e,
                )
                set_public_schema()


def with_public_schema(func):
    """Run func with search_path set to public, then restore previous schema."""
    previous_schema = get_current_schema()
    try:
        set_public_schema()
        return func()
    finally:
        if previous_schema == "public":
            set_public_schema()
        else:
            try:
                set_tenant_schema(previous_schema)
            except Exception as e:
                logger.warning(
                    "with_public_schema: failed to restore tenant %s, resetting to public: %s",
                    previous_schema,
                    e,
                )
                set_public_schema()


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
            try:
                set_tenant_schema(previous_schema)
            except Exception as e:
                logger.warning(
                    "get_public_user_by_id: failed to restore tenant %s, resetting to public: %s",
                    previous_schema,
                    e,
                )
                set_public_schema()

# =============================================================================
# RUN IN TENANT SCHEMA (sync + async for WebSocket consumers)
# =============================================================================
# In ASGI/Channels, each sync_to_async call can use a different DB connection.
# Use run_in_tenant_schema_async(schema_name, sync_func) so the same connection
# is used for SET search_path and the subsequent queries (per-message isolation).


def run_in_tenant_schema(schema_name, sync_func):
    """
    Run sync_func with search_path set to schema_name, then restore.
    Use this inside database_sync_to_async in WebSocket consumers so one
    connection is used for SET search_path and the DB work.
    """
    with schema_context(schema_name):
        return sync_func()


async def run_in_tenant_schema_async(schema_name, sync_func):
    """
    Run sync_func in tenant schema on a single DB connection (Channels).
    Use in WebSocket consumer methods that touch the DB for reliable
    per-message schema isolation.
    """
    from channels.db import database_sync_to_async
    return await database_sync_to_async(run_in_tenant_schema)(schema_name, sync_func)


# =============================================================================
# ASYNC SCHEMA SWITCHING (Django Channels)
# =============================================================================
# Legacy helpers; per-connection isolation is not guaranteed when using
# set_tenant_schema_async in middleware and then separate DB calls in the consumer.
# Prefer run_in_tenant_schema_async in consumer methods.

async def set_tenant_schema_async(schema_name):
    await sync_to_async(set_tenant_schema)(schema_name)


async def set_public_schema_async():
    await sync_to_async(set_public_schema)()


async def reset_tenant_schema_async():
    await sync_to_async(reset_tenant_schema)()


async def schema_exists_async(schema_name):
    return await sync_to_async(schema_exists)(schema_name)


async def schema_ready_async(schema_name, table_name="groups_group"):
    return await sync_to_async(schema_ready)(schema_name, table_name=table_name)

