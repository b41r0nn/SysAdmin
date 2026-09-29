import logging
import os

from django.conf import settings
from django.db.models import Max
from django.template.loader import render_to_string
from django.utils import timezone

from yule.client import build_client, OCSClientException

from .constants import PARTES_POR_TIPO

logger = logging.getLogger(__name__)

LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "img", "logo_redihos_mark.png")


#: OCS devuelve la cadena "Unavailable" cuando el agente no reporta el dato.
SIN_DATO_OCS = "unavailable"


def detalle_snapshot_software_ocs(activo):
    """Software instalado de un activo desde OCS, con el motivo si no se pudo.

    A diferencia de snapshot_software_ocs(), que solo devuelve la lista y
    silencia cualquier fallo, esto distingue los tres motivos por los que la
    lista puede venir vacía. Sin eso la vista no puede explicarle al usuario
    por qué no ve nada: "no hay nada instalado", "el equipo no está vinculado"
    y "OCS no responde" son tres cosas muy distintas.

    Returns:
        dict con:
            software: lista de dicts {"name", "version", "publisher"}
            estado:    "ok" | "sin_equipo" | "no_configurado" | "error"
            detalle:   texto para el usuario cuando estado != "ok"
    """
    equipo = activo.equipo_ocs.first() if hasattr(activo, "equipo_ocs") else None
    if not equipo or not equipo.id_ocs:
        return {
            "software": [],
            "estado": "sin_equipo",
            "detalle": (
                "Este activo no está vinculado a ningún equipo de OCS, "
                "así que no hay inventario de software para él."
            ),
        }

    try:
        client = build_client()
        if not client.is_configured():
            return {
                "software": [],
                "estado": "no_configurado",
                "detalle": (
                    "La conexión con el servidor OCS no está configurada. "
                    "Cargala en Yule › Configuración OCS."
                ),
            }
        software = client.get_software(str(equipo.id_ocs))
    except OCSClientException as exc:
        logger.warning("No se pudo obtener software OCS para %s: %s", activo.serial, exc)
        return {
            "software": [],
            "estado": "error",
            "detalle": f"El servidor OCS no respondió: {exc}",
        }
    except Exception as exc:
        logger.warning("Error snapshot OCS para %s: %s", activo.serial, exc)
        return {
            "software": [],
            "estado": "error",
            "detalle": f"Ocurrió un error al consultar OCS: {exc}",
        }

    # OCS devuelve el software en el orden en que lo reporta el agente, que no
    # es estable entre sincronizaciones. Ordenar acá evita que la lista "salte"
    # de una recarga a otra.
    software = sorted(
        software or [],
        key=lambda s: ((s.get("name") or "").strip().lower(), (s.get("version") or "").strip().lower()),
    )
    return {"software": software, "estado": "ok", "detalle": ""}


def snapshot_software_ocs(activo):
    """Captura el software instalado de un activo desde OCS (best-effort).

    Busca el EquipoOCS vinculado al activo (activo_local). Si OCS no está
    configurado/alcanzable o el equipo no está vinculado, devuelve [].

    Returns:
        Lista de dicts {"name", "version", "publisher"} (puede ser []).
    """
    return detalle_snapshot_software_ocs(activo)["software"]


def _acciones_marcadas(orden):
    acciones = []
    if orden.accion_limpieza_general:
        acciones.append("Limpieza general")
    if orden.accion_mantenimiento_logico:
        acciones.append("Mantenimiento lógico")
    if orden.accion_cambio_pasta_termica:
        acciones.append("Cambio de pasta térmica")
    if orden.accion_cambio_parte:
        acciones.append("Cambio de parte")
    return acciones


def _estado_partes_etiquetado(activo, orden):
    labels = dict(PARTES_POR_TIPO.get(activo.tipo_dispositivo, []))
    return [
        (labels.get(slug, slug), estado)
        for slug, estado in (orden.estado_partes or {}).items()
    ]


def hoja_de_vida_pdf_bytes(activo):
    """Renderiza la hoja de vida completa de un activo como PDF (multi-página).

    Incluye datos del activo, asignación actual, historial completo de órdenes de
    mantenimiento, software del último snapshot OCS y todas las fotos agrupadas
    por orden.
    """
    import weasyprint  # import local: en Windows dev se mockea en tests

    from administracion.models import ConfiguracionSistema
    from .models import OrdenMantenimiento

    ordenes = (
        OrdenMantenimiento.objects.filter(activo=activo)
        .select_related("plan", "activo")
        .prefetch_related("fotos")
        .order_by("-fecha_apertura", "-fecha_creacion")
    )
    ultima = ordenes.first()
    asignacion_actual = (
        activo.asignaciones.filter(activa=True).select_related("usuario").first()
    )
    equipo_ocs = (
        activo.equipo_ocs.first()
        if hasattr(activo, "equipo_ocs") and activo.equipo_ocs.exists()
        else None
    )

    software_ultimo = []
    if ultima and ultima.software_snapshot:
        software_ultimo = ultima.software_snapshot
        if (
            isinstance(software_ultimo, list)
            and software_ultimo
            and isinstance(software_ultimo[0], dict)
        ):
            software_ultimo = [
                s.get("name") if isinstance(s, dict) else str(s)
                for s in software_ultimo
            ]

    ordenes_detalle = [
        {
            "orden": o,
            "acciones": _acciones_marcadas(o),
            "estado_partes": _estado_partes_etiquetado(activo, o),
            "fotos": [
                {"path": f.foto.path, "descripcion": f.descripcion}
                for f in o.fotos.all()
            ],
        }
        for o in ordenes
    ]

    html = render_to_string("mantenimiento/hoja_de_vida_pdf.html", {
        "activo": activo,
        "ordenes_detalle": ordenes_detalle,
        "ultima": ultima,
        "asignacion_actual": asignacion_actual,
        "equipo_ocs": equipo_ocs,
        "software_ultimo": software_ultimo,
        "config": ConfiguracionSistema.get_config(),
        "logo_path": LOGO_PATH,
        "generado": timezone.now(),
    })
    # base_url debe ser string; settings.BASE_DIR es un pathlib.Path en Docker
    return weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()


def _activos_con_ultimo_mantenimiento():
    """Filas del reporte por activo: un activo por fila con su última fecha de
    mantenimiento cerrado (`fecha_cierre` más reciente). Solo activos con al
    menos una orden cerrada."""
    from inventario.models import Activo
    from .models import OrdenMantenimiento

    agrupado = (
        OrdenMantenimiento.objects.filter(estado="cerrada")
        .values("activo_id")
        .annotate(ultima_cierre=Max("fecha_cierre"))
        .order_by("activo_id")
    )
    ultimas = {fila["activo_id"]: fila["ultima_cierre"] for fila in agrupado}
    activos = Activo.objects.filter(pk__in=ultimas).order_by(
        "tipo_dispositivo", "marca", "modelo"
    )
    return [{"activo": a, "ultima_cierre": ultimas[a.pk]} for a in activos]


def reporte_activos_pdf_bytes():
    """Renderiza el reporte de activos con mantenimiento realizado como PDF.

    Una fila por activo (Serial, Marca/Modelo, Tipo y fecha del último
    mantenimiento cerrado). No reutiliza el reporte general de órdenes.
    """
    import weasyprint  # import local: en Windows dev se mockea en tests

    from administracion.models import ConfiguracionSistema

    filas = _activos_con_ultimo_mantenimiento()
    html = render_to_string("mantenimiento/reporte_activos_pdf.html", {
        "filas": filas,
        "config": ConfiguracionSistema.get_config(),
        "logo_path": LOGO_PATH,
        "generado": timezone.now(),
    })
    # base_url debe ser string; settings.BASE_DIR es un pathlib.Path en Docker
    return weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()