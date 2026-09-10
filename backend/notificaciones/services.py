from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from accounts.permisos import PERMISOS_POR_ROL
from inventario.models import ActaAsignacion, Activo
from licencias.models import DIAS_AVISO_VENCIMIENTO, LicenciaSoftware
from mantenimiento.models import PlanMantenimiento
from notificaciones.models import Notificacion
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