#TODO: If I gonna need this hook , I use it base.py with SPECTACULAR_SETTINGS

from django.db import connection

def custom_preprocessing_hook(endpoints):
    filtered = []

    for path, path_regex, method, callback in endpoints:

        if path.startswith('/admin/'):
            continue

        if path == '/health/':
            continue

        filtered.append((path, path_regex, method, callback))

    return filtered

def set_schema_for_spectacular():
    from apps.organizations.models import Organization

    try:
        organization = Organization.objects.filter(status='ACTIVE').first()
        if organization:
            connection.set_tenant(organization)
            return organization.schema_name

    except Exception:
        pass

    return 'public'