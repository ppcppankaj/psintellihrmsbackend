"""
File Upload Validators — Enterprise Security

Validates uploaded files with:
  1. Extension whitelist
  2. MIME type whitelist
  3. Magic-bytes verification
  4. Maximum file size enforcement

Usage in serializers:
    from apps.core.upload_validators import validate_upload

    class MySerializer(serializers.ModelSerializer):
        file = serializers.FileField(validators=[validate_upload])
"""

import logging
import mimetypes

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# ── Defaults (override via settings) ────────────────────────────────────────

MAX_UPLOAD_SIZE_MB = getattr(settings, "MAX_UPLOAD_SIZE_MB", 10)
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS = getattr(settings, "ALLOWED_UPLOAD_EXTENSIONS", {
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".rtf",
    ".ppt", ".pptx", ".odt", ".ods", ".odp",
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".ico",
    # Archives (optional — tighten if not needed)
    ".zip",
})

ALLOWED_MIME_TYPES = getattr(settings, "ALLOWED_UPLOAD_MIME_TYPES", {
    # Documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "text/plain",
    "application/rtf",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    # Images
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/bmp",
    "image/webp",
    "image/x-icon",
    "image/vnd.microsoft.icon",
    # Archives
    "application/zip",
    "application/x-zip-compressed",
})

# Magic bytes → expected MIME prefix mapping
_MAGIC_BYTES = {
    b"\x89PNG":       "image/png",
    b"\xff\xd8\xff":  "image/jpeg",
    b"GIF8":          "image/gif",
    b"%PDF":          "application/pdf",
    b"PK":            "application/",       # zip, docx, xlsx, pptx
    b"\xd0\xcf\x11":  "application/",      # MS Office legacy
    b"RIFF":          "image/webp",         # RIFF....WEBP
}


def _check_magic_bytes(file_obj):
    """
    Read first 8 bytes and verify against known magic-byte signatures.
    Returns True if the signature is recognized and consistent.
    Falls back to True for unrecognized signatures (text files, CSV, etc.).
    """
    file_obj.seek(0)
    header = file_obj.read(8)
    file_obj.seek(0)

    if not header:
        return False

    for magic, expected_prefix in _MAGIC_BYTES.items():
        if header.startswith(magic):
            # The file claims to be this type — verify content_type matches
            content_type = getattr(file_obj, "content_type", "") or ""
            if not content_type.startswith(expected_prefix):
                return False
            return True

    # No magic-byte match — could be text/csv/rtf etc. That's OK.
    return True


def validate_upload(file_obj):
    """
    Central file-upload validator.

    Raises ``ValidationError`` on:
      - Oversized file
      - Disallowed extension
      - Disallowed MIME type
      - Magic-byte / content-type mismatch
    """
    import os

    # ── 1. Size check ────────────────────────────────────────────────────
    size = getattr(file_obj, "size", None)
    if size is not None and size > MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError(
            f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE_MB} MB."
        )

    # ── 2. Extension check ───────────────────────────────────────────────
    name = getattr(file_obj, "name", "") or ""
    _, ext = os.path.splitext(name)
    ext = ext.lower()

    if ext and ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"File extension '{ext}' is not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # ── 3. MIME type check ───────────────────────────────────────────────
    content_type = getattr(file_obj, "content_type", None)
    if not content_type:
        # Guess from extension
        content_type, _ = mimetypes.guess_type(name)

    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise ValidationError(
            f"File type '{content_type}' is not allowed."
        )

    # ── 4. Magic-byte verification ───────────────────────────────────────
    if hasattr(file_obj, "read"):
        if not _check_magic_bytes(file_obj):
            logger.warning(
                "upload_magic_byte_mismatch file=%s content_type=%s",
                name,
                content_type,
            )
            raise ValidationError(
                "File content does not match its declared type."
            )

    return file_obj


class SecureFileField:
    """
    Drop-in DRF serializer field validator.
    Use as: file = serializers.FileField(validators=[SecureFileField()])
    """

    def __call__(self, value):
        return validate_upload(value)
