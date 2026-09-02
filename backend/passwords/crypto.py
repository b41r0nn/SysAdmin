import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def build_fernet():
    raw_key = getattr(settings, "PASSWORDS_ENCRYPTION_KEY", "")
    if raw_key:
        key = raw_key.encode("utf-8")
    else:
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)
