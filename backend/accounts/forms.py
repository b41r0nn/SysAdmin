from django.contrib.auth.forms import AuthenticationForm


class SysAdminAuthenticationForm(AuthenticationForm):
    """Form de login con mensajes genéricos: no revela si el usuario existe."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Usuario o contraseña incorrectos.",
        "inactive": "Esta cuenta está inactiva. Contacte al administrador.",
    }
