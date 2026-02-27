import base64
from cryptography.fernet import Fernet
from django.conf import settings

class SymmetricEncryption:
    """
    Utility class for symmetric encryption using Fernet (AES).
    Uses ENCRYPTION_KEY from settings.
    """
    
    def __init__(self):
        # Fernet key must be 32 url-safe base64-encoded bytes
        key = settings.ENCRYPTION_KEY
        if isinstance(key, str):
            # Ensure it's 32 bytes and base64 encoded
            # If it's a plain string, we hash it to get a consistent 32-byte key
            import hashlib
            key = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        self.fernet = Fernet(key)

    def encrypt(self, plain_text: str) -> str:
        """Encrypt plain text to a base64 encoded token"""
        if not plain_text:
            return ""
        return self.fernet.encrypt(plain_text.encode()).decode()

    def decrypt(self, encrypted_text: str) -> str:
        """Decrypt a base64 encoded token to plain text"""
        if not encrypted_text:
            return ""
        try:
            return self.fernet.decrypt(encrypted_text.encode()).decode()
        except Exception:
            # If decryption fails, it might be plain text or corrupted
            return encrypted_text

_encryption_instance = None

def get_encryption():
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = SymmetricEncryption()
    return _encryption_instance

def encrypt_value(value: str) -> str:
    return get_encryption().encrypt(value)

def decrypt_value(value: str) -> str:
    return get_encryption().decrypt(value)
