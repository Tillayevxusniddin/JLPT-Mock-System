from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        import traceback
        import sys
        if hasattr(exc, '__traceback__'):
            tb_str = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            return Response(
                {"detail": f"An unexpected server error occurred: {str(exc)}", "traceback": tb_str},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(
            {"detail": f"An unexpected server error occurred: {str(exc)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            "error": response.data,
            "message": "An error occurred",
            "status_code": response.status_code,
        },
        status=response.status_code,
    )
