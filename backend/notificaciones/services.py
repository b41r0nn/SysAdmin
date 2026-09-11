from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage, get_connection
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone

from accounts.permisos import PERMISOS_POR_ROL
from administracion.models import ConfiguracionSistema
from inventario.models import ActaAsignacion, Activo
from inventario.services import acta_pdf_bytes
from licencias.models import DIAS_AVISO_VENCIMIENTO, LicenciaSoftware
from mantenimiento.models import PlanMantenimiento
from notificaciones.models import Notificacion, NotificacionEmail
from yule.models import EquipoOCS


DIAS_GARANTIA = 30
DIAS_MANTENIMIENTO = 7


def _puede_ver(user, modulo):
    perm = PERMISOS_POR_ROL.get(user.rol, {})
    return perm.get(modulo) in ("lectura", "escritura")


def _crear(user, tipo, titulo, mensaje, link="", objetokey=""):
    _, creada = Notificacion.objects.get_or_create(
        usuario=user,
        tipo=tipo,
        objetokey=objetokey,
        defaults={"titulo": titulo, "mensaje": mensaje, "link": link},
    )
    return creada


def _detectar_garantias(user):
    hoy = timezone.localdate()
    limite = hoy + timedelta(days=DIAS_GARANTIA)
    activos = (
        Activo.objects.filter(
            fecha_compra__isnull=False,
            garantia_fabrica_meses__gt=0,
        )
        .exclude(estado="dado_de_baja")
    )
    for activo in activos:
        vencimiento = activo.fecha_vencimiento_garantia
        if not vencimiento:
            continue
        link = reverse("inventario:detalle", args=[activo.pk])
        if vencimiento < hoy:
            _crear(
                user,
                "garantia",
                f"Garantía vencida · {activo.serial}",
                f"La garantía de {activo.get_tipo_dispositivo_display()} "
                f"{activo.marca} {activo.modelo} venció el {vencimiento:%d/%m/%Y}.",
                link=link,
                objetokey=f"garantia:{activo.pk}",
            )
        elif vencimiento <= limite:
            _crear(
                user,
                "garantia",
                f"Garantía por vencer · {activo.serial}",
                f"La garantía de {activo.get_tipo_dispositivo_display()} "
                f"{activo.marca} {activo.modelo} vence el {vencimiento:%d/%m/%Y}.",
                link=link,
                objetokey=f"garantia:{activo.pk}",
            )


def _detectar_mantenimiento(user):
    hoy = timezone.localdate()
    limite = hoy + timedelta(days=DIAS_MANTENIMIENTO)
    planes = (
        PlanMantenimiento.objects.filter(
            estado="activo",
            proxima_ejecucion__isnull=False,
        ).select_related("activo")
    )
    creadas = 0
    for plan in planes:
        link = reverse("mantenimiento:lista_planes")
        if plan.proxima_ejecucion < hoy:
            creadas += _crear(
                user,
                "mantenimiento",
                f"Mantenimiento atrasado · {plan.activo.serial}",
                f"El plan {plan.get_tipo_display()} del activo {plan.activo.serial} "
                f"debía ejecutarse el {plan.proxima_ejecucion:%d/%m/%Y}.",
                link=link,
                objetokey=f"mantenimiento:{plan.pk}",
            )
        elif plan.proxima_ejecucion <= limite:
            creadas += _crear(
                user,
                "mantenimiento",
                f"Mantenimiento próximo · {plan.activo.serial}",
                f"El plan {plan.get_tipo_display()} del activo {plan.activo.serial} "
                f"está programado para el {plan.proxima_ejecucion:%d/%m/%Y}.",
                link=link,
                objetokey=f"mantenimiento:{plan.pk}",
            )
    return creadas


def _detectar_actas(user):
    actas = (
        ActaAsignacion.objects.filter(
            Q(escaneado_firmado="") | Q(escaneado_firmado__isnull=True)
        ).select_related("asignacion__activo")
    )
    for acta in actas:
        activo = acta.asignacion.activo
        link = reverse("inventario:detalle", args=[activo.pk])
        _crear(
            user,
            "acta",
            f"Acta pendiente de firma · #{acta.pk}",
            f"El acta #{acta.pk} del activo {activo.serial} aún no tiene la firma escaneada cargada.",
            link=link,
            objetokey=f"acta:{acta.pk}",
        )


def _detectar_ocs(user):
    sin_match = EquipoOCS.objects.filter(activo_local__isnull=True).count()
    if sin_match:
        _crear(
            user,
            "ocs",
            "Equipos OCS sin vincular",
            f"Hay {sin_match} equipos detectados por OCS Inventory que aún no están vinculados a un activo del inventario.",
            link=reverse("yule:equipos_sin_match"),
            objetokey="ocs:sin_match",
        )


def _detectar_licencias(user):
    hoy = timezone.localdate()
    limite = hoy + timedelta(days=DIAS_AVISO_VENCIMIENTO)
    licencias = LicenciaSoftware.objects.filter(
        fecha_vencimiento__isnull=False,
    ).exclude(estado="cancelada")
    for lic in licencias:
        link = reverse("licencias:detalle", args=[lic.pk])
        version = f" {lic.version}" if lic.version else ""
        objetokey = f"licencia:{lic.pk}"
        if lic.fecha_vencimiento < hoy:
            _crear(
                user,
                "licencia",
                f"Licencia vencida · {lic.nombre}",
                f"La licencia {lic.nombre}{version} venció el {lic.fecha_vencimiento:%d/%m/%Y}.",
                link=link,
                objetokey=objetokey,
            )
        elif lic.fecha_vencimiento <= limite:
            _crear(
                user,
                "licencia",
                f"Licencia por vencer · {lic.nombre}",
                f"La licencia {lic.nombre}{version} vence el {lic.fecha_vencimiento:%d/%m/%Y}.",
                link=link,
                objetokey=objetokey,
            )


def generar_mantenimiento(user):
    if _puede_ver(user, "mantenimiento"):
        return _detectar_mantenimiento(user)
    return 0


def generar_notificaciones_mantenimiento():
    """Comando: genera notificaciones de mantenimiento para todos los usuarios
    activos con acceso al módulo. Idempotente por (usuario, tipo, objetokey)."""
    total = 0
    for user in get_user_model().objects.filter(is_active=True):
        total += generar_mantenimiento(user)
    return total


def aviso_usuario(user, titulo, mensaje, link="", objetokey=""):
    """Crea una notificación tipo 'aviso' (idempotente por objetokey)."""
    return _crear(user, "aviso", titulo, mensaje, link, objetokey)


def generar_notificaciones(user):
    """Genera (de forma idempotente) las notificaciones vigentes para el usuario.

    Se ejecuta al consultar la bandeja / la campana; al ser get_or_create sobre
    (usuario, tipo, objetokey) no duplica notificaciones ya registradas.
    """
    if not user or not user.is_authenticated:
        return

    if _puede_ver(user, "inventario"):
        _detectar_garantias(user)
        _detectar_actas(user)
        _detectar_ocs(user)
    if _puede_ver(user, "licencias"):
        _detectar_licencias(user)
    generar_mantenimiento(user)


# ── Cola de emails (patrón GLPI: cola + cron) ────────────────────────────────


def encolar_email(destinatario_email, asunto, cuerpo, adjunto_tipo="", adjunto_objeto_id=None):
    """Encola un email. Sin destinatario → sin acción, no es error.

    El envío real lo hace el comando `enviar_notificaciones_email` (cron).
    """
    if not destinatario_email:
        return None
    return NotificacionEmail.objects.create(
        destinatario=destinatario_email,
        asunto=asunto,
        cuerpo=cuerpo,
        adjunto_tipo=adjunto_tipo,
        adjunto_objeto_id=adjunto_objeto_id,
    )


def _get_smtp_connection():
    config = ConfiguracionSistema.get_config()
    if not config.smtp_host:
        return None  # sin config SMTP → no enviar (no es error)
    return get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=config.smtp_host,
        port=config.smtp_puerto or 587,
        username=config.smtp_usuario,
        password=config.get_smtp_password(),
        use_tls=config.smtp_usa_tls,
        use_ssl=config.smtp_usa_ssl,
    )


def _adjunto_acta(objeto_id):
    acta = ActaAsignacion.objects.get(pk=objeto_id)
    pdf = acta_pdf_bytes(acta.asignacion)
    nombre = f"acta_{acta.asignacion.activo.serial}_{acta.asignacion.usuario.documento_identidad}.pdf"
    return (nombre, pdf, "application/pdf")


def procesar_cola_email():
    """Despacha la cola de emails. Reintenta hasta 5 intentos.

    Devuelve (total, enviados, fallos, quedan). Si falla la conexión SMTP
    (host caído / credenciales malas / firewall) marca toda la corrida con
    intentos+1 y el error, y sale limpio: el cron nunca revienta y la tabla
    NotificacionEmail queda con el rastro.
    """
    config = ConfiguracionSistema.get_config()
    if not config.smtp_host:
        return 0, 0, 0, 0  # sin config SMTP → no es error

    pending = NotificacionEmail.objects.filter(
        enviado=False, intentos__lt=5
    ).order_by("fecha_creacion")
    total = pending.count()

    connection = _get_smtp_connection()
    try:
        try:
            connection.open()
        except Exception as exc:
            error = str(exc)[:2000]
            marcadas = pending.update(intentos=F("intentos") + 1, error=error)
            quedan = NotificacionEmail.objects.filter(enviado=False, intentos__lt=5).count()
            return total, 0, marcadas, quedan

        enviados = 0
        fallos = 0
        for correo in pending:
            try:
                adjuntos = []
                if correo.adjunto_tipo == "acta" and correo.adjunto_objeto_id:
                    adjuntos.append(_adjunto_acta(correo.adjunto_objeto_id))
                mensaje = EmailMessage(
                    subject=correo.asunto,
                    body=correo.cuerpo,
                    to=[correo.destinatario],
                    attachments=adjuntos,
                    connection=connection,
                )
                mensaje.send(fail_silently=False)
                correo.enviado = True
                correo.intentos += 1
                correo.fecha_enviado = timezone.now()
                correo.error = ""
                correo.save(update_fields=["enviado", "intentos", "fecha_enviado", "error"])
                enviados += 1
            except Exception as exc:
                correo.intentos += 1
                correo.error = str(exc)[:2000]
                correo.save(update_fields=["intentos", "error"])
                fallos += 1
    finally:
        try:
            connection.close()
        except Exception:
            pass

    return total, enviados, fallos, NotificacionEmail.objects.filter(enviado=False, intentos__lt=5).count()