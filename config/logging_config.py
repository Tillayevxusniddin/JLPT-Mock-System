"""
Logging configuration for Django with JSON formatting for Loki/Promtail.
...
"""

import json
import logging
from datetime import datetime
from django.conf import settings
from apps.core.middleware import get_current_request

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        
        if hasattr(record, 'schema_name'):
            log_data['schema_name'] = record.schema_name

        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'ip_address'):
            log_data['ip_address'] = record.ip_address
        if hasattr(record, 'path'):
            log_data['path'] = record.path
        if hasattr(record, 'method'):
            log_data['method'] = record.method
        if hasattr(record, 'status_code'):
            log_data['status_code'] = record.status_code
        
        return json.dumps(log_data, ensure_ascii=False)

class RequestIDFilter(logging.Filter):
    def filter(self, record):
        try:
            request = get_current_request()

            if request:
                record.request_id = getattr(request, 'id', None)
                record.path = getattr(request, 'path', None)
                record.method = getattr(request, 'method', None)
                
                if hasattr(request, 'user') and request.user.is_authenticated:
                    record.user_id = request.user.id
                
                schema_name = getattr(request, 'tenant_schema', None)

                if schema_name:
                    record.schema_name = schema_name
                else:
                    if hasattr(request, 'user') and request.user.is_authenticated:
                        if hasattr(request.user, 'center') and request.user.center:
                            record.schema_name = request.user.center.schema_name
                        else:
                            record.schema_name = 'public'
                    else:
                        record.schema_name = 'public'

        except Exception:
            pass

        return True