from django.contrib.auth import signals as auth_signals
from django.dispatch import receiver

from core.utils import get_client_ip
from .models import RegistroAuditoria


@receiver(auth_signals.user_logged_in)
def _auditoria_login(sender, request, user, **kwargs):
    RegistroAuditoria.objects.create(
        usuario=user,
        modulo="auth",
        accion="login",
        detalle=f"El usuario {user.username} inició sesión.",
        ip=get_client_ip(request),
    )


@receiver(auth_signals.user_logged_out)
def _auditoria_logout(sender, request, user, **kwargs):
    RegistroAuditoria.objects.create(
        usuario=user,
        modulo="auth",
        accion="logout",
        detalle=f"El usuario {getattr(user, 'username', 'desconocido')} cerró sesión.",
        ip=get_client_ip(request),
    )
