"""
Custom Exception Handler for DRF
"""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, Throttled
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
import logging

logger = logging.getLogger(__name__)
security_logger = logging.getLogger("security.audit")


def custom_exception_handler(exc, context):
    """
    Custom exception handler that provides consistent error responses.
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    if response is not None:
        _log_security_event(exc, context, response.status_code)
        # Customize the response format
        custom_response_data = {
            'success': False,
            'error': {
                'code': response.status_code,
                'message': get_error_message(response.data),
                'details': response.data if isinstance(response.data, dict) else {'detail': response.data},
            }
        }
        response.data = custom_response_data
        return response
    
    # Handle Django ValidationError
    if isinstance(exc, DjangoValidationError):
        logger.warning(f"Validation error: {exc}")
        return Response(
            {
                'success': False,
                'error': {
                    'code': 400,
                    'message': 'Validation Error',
                    'details': {'validation_errors': exc.messages if hasattr(exc, 'messages') else [str(exc)]},
                }
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Handle 404
    if isinstance(exc, Http404):
        return Response(
            {
                'success': False,
                'error': {
                    'code': 404,
                    'message': 'Not Found',
                    'details': {'detail': str(exc)},
                }
            },
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Log unexpected exceptions
    logger.exception(f"Unexpected error: {exc}")
    
    # Return generic error for unexpected exceptions
    return Response(
        {
            'success': False,
            'error': {
                'code': 500,
                'message': 'Internal Server Error',
                'details': {'detail': 'An unexpected error occurred.'},
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def _log_security_event(exc, context, status_code):
    if status_code not in (401, 403, 429):
        return

    request = context.get("request")
    if request is None:
        return

    user = getattr(request, "user", None)
    user_id = getattr(user, "id", None) if user and getattr(user, "is_authenticated", False) else None
    exc_name = exc.__class__.__name__
    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        event_type = "auth_failed"
    elif isinstance(exc, PermissionDenied):
        event_type = "permission_denied"
    elif isinstance(exc, Throttled):
        event_type = "throttled"
    else:
        event_type = "security_event"

    security_logger.warning(
        "api_security_event type=%s status=%s method=%s path=%s user_id=%s ip=%s error=%s",
        event_type,
        status_code,
        request.method,
        request.path,
        user_id,
        request.META.get("REMOTE_ADDR"),
        exc_name,
    )


def get_error_message(data):
    """Extract a user-friendly error message from response data"""
    if isinstance(data, dict):
        if 'detail' in data:
            return str(data['detail'])
        if 'non_field_errors' in data:
            return str(data['non_field_errors'][0])
        # Get first error message
        for key, value in data.items():
            if isinstance(value, list) and value:
                return f"{key}: {value[0]}"
            elif isinstance(value, str):
                return f"{key}: {value}"
    elif isinstance(data, list) and data:
        return str(data[0])
    return str(data)


class APIException(Exception):
    """Base exception for API errors"""
    
    def __init__(self, message, code=None, status_code=status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.code = code or 'error'
        self.status_code = status_code
        super().__init__(message)


class ValidationException(APIException):
    """Validation error exception"""
    
    def __init__(self, message, field=None):
        super().__init__(message, code='validation_error', status_code=status.HTTP_400_BAD_REQUEST)
        self.field = field


class PermissionDeniedException(APIException):
    """Permission denied exception"""
    
    def __init__(self, message="You do not have permission to perform this action"):
        super().__init__(message, code='permission_denied', status_code=status.HTTP_403_FORBIDDEN)


class ResourceNotFoundException(APIException):
    """Resource not found exception"""
    
    def __init__(self, resource_type, resource_id=None):
        message = f"{resource_type} not found"
        if resource_id:
            message = f"{resource_type} with ID {resource_id} not found"
        super().__init__(message, code='not_found', status_code=status.HTTP_404_NOT_FOUND)


class ConflictException(APIException):
    """Conflict exception (e.g., duplicate resource)"""
    
    def __init__(self, message):
        super().__init__(message, code='conflict', status_code=status.HTTP_409_CONFLICT)


class RateLimitException(APIException):
    """Rate limit exceeded exception"""
    
    def __init__(self, message="Rate limit exceeded. Please try again later."):
        super().__init__(message, code='rate_limit', status_code=status.HTTP_429_TOO_MANY_REQUESTS)
