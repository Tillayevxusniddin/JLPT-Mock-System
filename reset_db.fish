#!/usr/bin/env fish
# Database Reset Script for Fish Shell
# WARNING: Development environment ONLY!

# Colors
set -g RED '\033[0;31m'
set -g GREEN '\033[0;32m'
set -g YELLOW '\033[1;33m'
set -g BLUE '\033[0;34m'
set -g NC '\033[0m' # No Color

echo ""
echo (set_color --bold brmagenta)"╔════════════════════════════════════════════════════════════════════╗"
echo (set_color --bold brmagenta)"║      DATABASE & MIGRATION RESET SCRIPT (DEVELOPMENT ONLY)         ║"
echo (set_color --bold brmagenta)"╚════════════════════════════════════════════════════════════════════╝"(set_color normal)
echo ""

# Check if in development mode
if not test -f .env
    echo (set_color red)"✗ .env file not found!"(set_color normal)
    exit 1
end

# Warning
echo (set_color yellow)"⚠️  WARNING: This will DELETE ALL DATA in your database!"(set_color normal)
echo (set_color yellow)"⚠️  This operation is IRREVERSIBLE!"(set_color normal)
echo ""

# Confirmation
read -P (set_color --bold)"Type 'yes' to continue: "(set_color normal) confirm

if test "$confirm" != "yes"
    echo (set_color yellow)"Operation cancelled."(set_color normal)
    exit 0
end

echo ""
echo (set_color cyan)"Starting reset process..."(set_color normal)
echo ""

# Step 1: Delete all migration files except __init__.py
echo (set_color --bold blue)"STEP 1: Deleting migration files..."(set_color normal)
set deleted_count 0

for app_dir in apps/*/
    set migrations_dir $app_dir"migrations"
    if test -d $migrations_dir
        echo (set_color cyan)"  Processing: $migrations_dir"(set_color normal)
        
        # Delete __pycache__
        if test -d $migrations_dir"__pycache__"
            rm -rf $migrations_dir"__pycache__"
            echo (set_color green)"    ✓ Deleted __pycache__"(set_color normal)
        end
        
        # Delete all .py files except __init__.py
        for migration_file in $migrations_dir/*.py
            set filename (basename $migration_file)
            if test "$filename" != "__init__.py"
                rm -f $migration_file
                set deleted_count (math $deleted_count + 1)
                echo (set_color green)"    ✓ Deleted: $filename"(set_color normal)
            end
        end
        
        # Delete .pyc files
        for pyc_file in $migrations_dir/*.pyc
            if test -f $pyc_file
                rm -f $pyc_file
            end
        end
    end
end

echo (set_color green)"✓ Deleted $deleted_count migration files"(set_color normal)
echo ""

# Step 2: Drop database (using Python script is safer for multi-tenant)
echo (set_color --bold blue)"STEP 2: Dropping all database tables..."(set_color normal)
python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()
from django.db import connection

with connection.cursor() as cursor:
    if connection.vendor == 'postgresql':
        # Drop all tables in public schema
        cursor.execute(\"\"\"
            SELECT tablename FROM pg_tables WHERE schemaname = 'public'
        \"\"\")
        tables = cursor.fetchall()
        for table in tables:
            cursor.execute(f'DROP TABLE IF EXISTS public.{table[0]} CASCADE')
            print(f'  ✓ Dropped table: {table[0]}')
        
        # Drop tenant schemas
        cursor.execute(\"\"\"
            SELECT schema_name FROM information_schema.schemata 
            WHERE schema_name LIKE 'tenant_%'
        \"\"\")
        schemas = cursor.fetchall()
        for schema in schemas:
            cursor.execute(f'DROP SCHEMA IF EXISTS {schema[0]} CASCADE')
            print(f'  ✓ Dropped schema: {schema[0]}')
    else:
        cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
        tables = cursor.fetchall()
        for table in tables:
            if table[0] != 'sqlite_sequence':
                cursor.execute(f'DROP TABLE IF EXISTS {table[0]}')
                print(f'  ✓ Dropped table: {table[0]}')
print('✓ All tables dropped')
" 2>&1

echo (set_color green)"✓ Database tables dropped"(set_color normal)
echo ""

# Step 3: Create fresh migrations
echo (set_color --bold blue)"STEP 3: Creating fresh migrations..."(set_color normal)
python manage.py makemigrations
if test $status -eq 0
    echo (set_color green)"✓ Migrations created successfully"(set_color normal)
else
    echo (set_color red)"✗ Error creating migrations"(set_color normal)
    exit 1
end
echo ""

# Step 4: Apply migrations
echo (set_color --bold blue)"STEP 4: Applying migrations..."(set_color normal)
python manage.py migrate
if test $status -eq 0
    echo (set_color green)"✓ Migrations applied successfully"(set_color normal)
else
    echo (set_color red)"✗ Error applying migrations"(set_color normal)
    exit 1
end
echo ""

# Success
echo ""
echo (set_color --bold green)"╔════════════════════════════════════════════════════════════════════╗"
echo (set_color --bold green)"║                  ✅ RESET COMPLETE! ✅                             ║"
echo (set_color --bold green)"╚════════════════════════════════════════════════════════════════════╝"(set_color normal)
echo ""
echo (set_color cyan)"Next steps:"(set_color normal)
echo (set_color cyan)"  1. Create owner: python manage.py init_owner"(set_color normal)
echo (set_color cyan)"  2. Run server: python manage.py runserver"(set_color normal)
echo ""
