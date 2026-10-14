from django.conf import settings
from django.core.checks import Warning, register


@register()
def check_passwords_encryption_key(app_configs, **kwargs):
    """W001: la clave del vault debe estar definida explícitamente.

    Si falta, passwords.crypto.build_fernet() la deriva de SECRET_KEY: rotar
    SECRET_KEY deja ilegibles los secretos del vault y las claves SMTP/OCS.
    """
    if getattr(settings, "PASSWORDS_ENCRYPTION_KEY", ""):
        return []
    return [
        Warning(
            "PASSWORDS_ENCRYPTION_KEY no está configurado: la clave del vault "
            "se deriva de SECRET_KEY y una rotación de SECRET_KEY deja "
            "ilegibles los secretos guardados.",
            hint="Define PASSWORDS_ENCRYPTION_KEY (una clave Fernet) en .env.",
            id="sysadmin.W001",
        )
    ]
