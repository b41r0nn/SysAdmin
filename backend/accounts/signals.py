from axes.signals import user_locked_out
from django.contrib.auth import signals as auth_signals
from django.dispatch import receiver

from administracion.services import registrar_auditoria


def _request_ip(request):
    if not request or not request.META:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@receiver(auth_signals.user_login_failed)
def _auditoria_login_fallido(sender, credentials, request, **kwargs):
    username = credentials.get("username", "desconocido")
    registrar_auditoria(
        usuario=None,
        modulo="auth",
        accion="login_fallido",
        detalle=f"Intento de inicio de sesión fallido para el usuario '{username}'.",
        ip=_request_ip(request),
    )


@receiver(user_locked_out)
def _auditoria_cuenta_bloqueada(sender, request, username, ip_address, **kwargs):
    registrar_auditoria(
        usuario=None,
        modulo="auth",
        accion="cuenta_bloqueada",
        detalle=f"Cuenta bloqueada por intentos fallidos: usuario '{username}', IP {ip_address}.",
        ip=ip_address,
    )
