from django.contrib.auth import signals as auth_signals
from django.dispatch import receiver

from .models import RegistroAuditoria


def _request_ip(request):
    if not request or not request.META:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@receiver(auth_signals.user_logged_in)
def _auditoria_login(sender, request, user, **kwargs):
    RegistroAuditoria.objects.create(
        usuario=user,
        modulo="auth",
        accion="login",
        detalle=f"El usuario {user.username} inició sesión.",
        ip=_request_ip(request),
    )


@receiver(auth_signals.user_logged_out)
def _auditoria_logout(sender, request, user, **kwargs):
    RegistroAuditoria.objects.create(
        usuario=user,
        modulo="auth",
        accion="logout",
        detalle=f"El usuario {getattr(user, 'username', 'desconocido')} cerró sesión.",
        ip=_request_ip(request),
    )