# config/spectacular.py
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
    from apps.centers.models import Center

    try:
        center = Center.objects.filter(status='ACTIVE').first()
        if center:
            connection.set_tenant(center)
            return center.schema_name

    except Exception:
        pass

    return 'public'