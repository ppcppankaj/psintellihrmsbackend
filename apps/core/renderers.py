"""
Standard JSON renderer that wraps all DRF responses in a consistent envelope.

Success:  {"success": true,  "data": ..., "message": "OK"}
Error:    {"success": false, "error": {"code": ..., "message": ..., "details": ...}}

Pagination and exception-handler responses are already wrapped and passed through unchanged.
"""

from rest_framework.renderers import JSONRenderer


class StandardJSONRenderer(JSONRenderer):
    """
    Automatically wraps raw DRF responses in the standard JSON envelope.
    Skips wrapping if the response is already wrapped (pagination, exceptions).
    """

    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get('response') if renderer_context else None
        request = renderer_context.get('request') if renderer_context else None

        if data is None:
            data = {'success': True, 'data': None, 'message': 'OK'}
        elif isinstance(data, dict) and 'success' in data:
            # Already wrapped by pagination, exception handler, or manual wrapper
            pass
        elif response and response.status_code >= 400:
            # Error responses not caught by exception handler
            data = {
                'success': False,
                'error': {
                    'code': response.status_code,
                    'message': self._extract_message(data),
                    'details': data if isinstance(data, dict) else {'detail': data},
                },
            }
        else:
            # Normal success response — wrap
            method = getattr(request, 'method', 'GET') if request else 'GET'
            data = {
                'success': True,
                'data': data,
                'message': self._method_message(method),
            }

        return super().render(data, accepted_media_type, renderer_context)

    @staticmethod
    def _method_message(method):
        return {
            'POST': 'Created successfully.',
            'PUT': 'Updated successfully.',
            'PATCH': 'Updated successfully.',
            'DELETE': 'Deleted successfully.',
        }.get(method, 'OK')

    @staticmethod
    def _extract_message(data):
        if isinstance(data, dict):
            return data.get('detail', data.get('message', 'Error'))
        if isinstance(data, list) and data:
            return str(data[0])
        return str(data) if data else 'Error'
