from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from apps.core.openapi_serializers import EmptySerializer


class CompatNotImplementedView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def _response(self, detail: str):
        return Response(
            {
                "success": False,
                "detail": detail,
                "error_code": "NOT_IMPLEMENTED",
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    def get(self, request, *args, **kwargs):
        return self._response("This compatibility endpoint is not implemented.")

    def post(self, request, *args, **kwargs):
        return self._response("This compatibility endpoint is not implemented.")

    def put(self, request, *args, **kwargs):
        return self._response("This compatibility endpoint is not implemented.")

    def patch(self, request, *args, **kwargs):
        return self._response("This compatibility endpoint is not implemented.")

    def delete(self, request, *args, **kwargs):
        return self._response("This compatibility endpoint is not implemented.")


class DocumentCompatView(CompatNotImplementedView):
    """Placeholder for /api/v1/documents/* endpoints."""
    pass


class TrainingCompatView(CompatNotImplementedView):
    """Placeholder for /api/v1/training/* endpoints."""
    pass
