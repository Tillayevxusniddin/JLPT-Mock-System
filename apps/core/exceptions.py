from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.conf import settings

def custom_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = DRFValidationError(detail=exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)

    response = exception_handler(exc, context)

    if response is not None:
        return Response({
            "status": "error",
            "code": response.status_code,
            "message": "Validation Error" if response.status_code == 400 else "Error",
            "errors": response.data
        }, status=response.status_code)
    
    error_message = "Internal server error"
    if settings.DEBUG:
        error_message = str(exc)
        
    return Response({
        "status": "error",
        "code": 500,
        "message": error_message,
    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)