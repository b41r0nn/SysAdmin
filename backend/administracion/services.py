from .models import RegistroAuditoria


def registrar_auditoria(usuario, modulo, accion, objeto=None, detalle="", ip=""):
    """Helper para registrar una entrada de auditoría desde cualquier vista."""
    RegistroAuditoria.objects.create(
        usuario=usuario,
        modulo=modulo,
        accion=accion,
        objeto_tipo=objeto._meta.model_name if objeto else "",
        objeto_id=objeto.pk if objeto else None,
        detalle=detalle,
        ip=ip or None,
    )