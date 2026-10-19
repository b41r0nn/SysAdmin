import base64
import hashlib

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings


def _fernet_legado():
    """Clave derivada de SECRET_KEY (esquema anterior a PASSWORDS_ENCRYPTION_KEY)."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def build_fernet():
    """Cifrador de secretos.

    Con PASSWORDS_ENCRYPTION_KEY definida cifra con esa clave y sigue pudiendo
    descifrar lo guardado con la clave legada; `manage.py rotar_clave_vault`
    re-cifra esos datos con la clave nueva.
    """
    raw_key = getattr(settings, "PASSWORDS_ENCRYPTION_KEY", "")
    if raw_key:
        return MultiFernet([Fernet(raw_key.encode("utf-8")), _fernet_legado()])
    return _fernet_legado()
