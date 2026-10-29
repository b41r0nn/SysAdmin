from django.contrib.auth import signals as auth_signals
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.utils import get_client_ip
from .models import Modulo, RegistroAuditoria
from .registro import invalidar_cache


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


@receiver(post_save, sender=Modulo)
@receiver(post_delete, sender=Modulo)
def _invalidar_cache_de_modulos(sender, **kwargs):
    invalidar_cache()
