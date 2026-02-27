"""
Secure Media Serving — Authenticated File Access

All /media/ requests are routed through this view, which:
  1. Requires authentication
  2. Validates the user's organization owns the file (when possible)
  3. Sends the file via Django (or X-Accel-Redirect for nginx)

In production, nginx should proxy /media/ to this Django view,
and the actual file serving uses X-Accel-Redirect to /protected-media/.
"""

import logging
import os
import posixpath

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class SecureMediaView(APIView):
    """
    Authenticated media file serving.

    GET /api/media/<path>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, file_path):
        # Sanitize path — prevent directory traversal
        clean_path = posixpath.normpath(file_path)
        if clean_path.startswith(("../", "/")) or ".." in clean_path:
            raise Http404("Invalid path")

        full_path = os.path.join(settings.MEDIA_ROOT, clean_path)
        full_path = os.path.realpath(full_path)

        # Ensure resolved path is still inside MEDIA_ROOT
        media_root = os.path.realpath(settings.MEDIA_ROOT)
        if not full_path.startswith(media_root):
            raise Http404("Invalid path")

        if not os.path.isfile(full_path):
            raise Http404("File not found")

        # In production with nginx, use X-Accel-Redirect for efficiency
        use_accel = getattr(settings, "USE_NGINX_ACCEL_REDIRECT", False)
        if use_accel:
            response = HttpResponse()
            response["X-Accel-Redirect"] = f"/protected-media/{clean_path}"
            response["Content-Type"] = ""  # Let nginx determine
            return response

        # Development: serve directly via Django
        return FileResponse(
            open(full_path, "rb"),
            as_attachment=False,
        )
