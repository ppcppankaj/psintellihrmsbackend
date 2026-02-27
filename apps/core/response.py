"""
Standardized JSON response helpers.

All API responses follow the envelope:

    Success:  {"success": true,  "data": ..., "message": "..."}
    Error:    {"success": false, "error": {"code": 400, "message": "...", "details": {...}}}

Paginated responses (handled by ``StandardResultsPagination``) follow:

    {"success": true, "data": [...], "pagination": {...}}
"""

from rest_framework.response import Response
from rest_framework import status


def success_response(data=None, message='OK', http_status=status.HTTP_200_OK, **extra):
    """Return a successful JSON envelope."""
    payload = {'success': True, 'data': data, 'message': message}
    payload.update(extra)
    return Response(payload, status=http_status)


def success_detail_response(instance_data, message='OK'):
    """Return a single-object detail."""
    return success_response(data=instance_data, message=message)


def created_response(data=None, message='Created successfully.'):
    return success_response(data=data, message=message, http_status=status.HTTP_201_CREATED)


def deleted_response(message='Deleted successfully.'):
    return Response(
        {'success': True, 'data': None, 'message': message},
        status=status.HTTP_204_NO_CONTENT,
    )


def error_response(message='An error occurred.', details=None, http_status=status.HTTP_400_BAD_REQUEST):
    return Response(
        {
            'success': False,
            'error': {
                'code': http_status,
                'message': message,
                'details': details or {},
            },
        },
        status=http_status,
    )
