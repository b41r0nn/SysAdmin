"""Programación del mantenimiento por equipo: ¿a qué equipo le toca?

Módulo de lógica pura (sin vistas ni formularios). Las reglas son las de la
Parte B4 del diseño:

* El preventivo se repite cada ``frecuencia_meses`` de la plantilla del tipo,
  contados desde el último preventivo **completo** (cerrado y fuera de
  garantía). Los correctivos y los preventivos en garantía no mueven la fecha.
* Mientras el equipo está en garantía y nunca tuvo un preventivo completo, no
  le toca nada hasta que la garantía venza.
* Si no hay garantía calculable, "le toca desde" es el día en que se registró
  el equipo. Se usa esa fecha, y no la de hoy, para que no cambie cada día.
* Una fecha programada a mano gana sobre todo lo demás.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import F
from django.utils import timezone

from inventario.models import Activo, _add_months

from .models import OrdenMantenimiento, PlantillaChecklist, ProgramacionMantenimiento

# Días hacia adelante en que un equipo que está al día ya aparece en "Por hacer".
DIAS_PROXIMOS = 30

# La del modelo de la plantilla; solo se usa si un tipo no tiene plantilla.
FRECUENCIA_POR_DEFECTO = 12

PROGRAMADO = "programado"
LE_TOCA = "le_toca"
EN_GARANTIA = "en_garantia"
AL_DIA = "al_dia"


@dataclass(frozen=True)
class Situacion:
    """Dónde está un equipo respecto a su próximo preventivo."""

    activo: Activo
    estado: str  # "programado" | "le_toca" | "en_garantia" | "al_dia"
    le_toca_desde: date
    fecha_programada: date | None
    vencimiento_garantia: date | None
    # El último cerrado, de cualquier tipo (preventivo o correctivo).
    ultimo: OrdenMantenimiento | None


def activos_programables():
    """Equipos que entran en la programación.

    Son los de un tipo que tiene checklist (``PlantillaChecklist``), sin los
    dados de baja.
    """
    tipos = PlantillaChecklist.objects.values("tipo_dispositivo")
    return Activo.objects.filter(tipo_dispositivo__in=tipos).exclude(estado="dado_de_baja").order_by("serial", "pk")


def _cerradas(activo=None):
    """Órdenes cerradas, de la más reciente a la más antigua."""
    cerradas = OrdenMantenimiento.objects.filter(estado="cerrada")
    if activo is not None:
        cerradas = cerradas.filter(activo=activo)
    # Las viejas sin fecha de cierre van al final (PostgreSQL pone los NULL primero al descender).
    return cerradas.order_by(F("fecha_cierre").desc(nulls_last=True), "-pk")


def _es_preventivo_completo(orden):
    return orden.tipo == "preventivo" and not orden.en_garantia and orden.fecha_cierre is not None


def ultimo_preventivo_completo(activo):
    """El preventivo cerrado, fuera de garantía, con la fecha de cierre más reciente."""
    return _cerradas(activo).filter(tipo="preventivo", en_garantia=False, fecha_cierre__isnull=False).first()


def _frecuencia(tipo_dispositivo):
    plantilla = PlantillaChecklist.objects.filter(tipo_dispositivo=tipo_dispositivo).first()
    return plantilla.frecuencia_meses if plantilla else FRECUENCIA_POR_DEFECTO


def _le_toca_desde(activo, preventivo, frecuencia):
    if preventivo is not None:
        return _add_months(preventivo.fecha_cierre, frecuencia)
    vencimiento = activo.fecha_vencimiento_garantia
    if vencimiento is not None:
        return vencimiento
    return timezone.localdate(activo.fecha_creacion)


def fecha_le_toca(activo):
    """Fecha desde la que al equipo le toca su próximo preventivo."""
    return _le_toca_desde(activo, ultimo_preventivo_completo(activo), _frecuencia(activo.tipo_dispositivo))


def _armar(activo, hoy, frecuencia, preventivo, ultimo, fecha_programada):
    """Calcula la situación con los datos ya leídos (lo comparten ``situacion`` y ``tablero``)."""
    le_toca_desde = _le_toca_desde(activo, preventivo, frecuencia)
    vencimiento = activo.fecha_vencimiento_garantia
    if fecha_programada is not None:
        estado = PROGRAMADO
    elif le_toca_desde <= hoy:
        estado = LE_TOCA
    elif vencimiento is not None and hoy <= vencimiento and preventivo is None:
        estado = EN_GARANTIA
    else:
        estado = AL_DIA
    return Situacion(
        activo=activo,
        estado=estado,
        le_toca_desde=le_toca_desde,
        fecha_programada=fecha_programada,
        vencimiento_garantia=vencimiento,
        ultimo=ultimo,
    )


def situacion(activo, hoy=None):
    """Situación de un equipo en ``hoy`` (por defecto, la fecha local de hoy)."""
    hoy = hoy or timezone.localdate()
    programada = (
        ProgramacionMantenimiento.objects.filter(activo=activo).values_list("fecha_programada", flat=True).first()
    )
    return _armar(
        activo,
        hoy,
        _frecuencia(activo.tipo_dispositivo),
        ultimo_preventivo_completo(activo),
        _cerradas(activo).first(),
        programada,
    )


def tablero(hoy=None):
    """Todos los equipos programables, repartidos en las tres listas del tablero.

    * ``por_hacer``: programados, los que ya les toca y los que están al día
      pero les toca en los próximos ``DIAS_PROXIMOS`` días.
    * ``en_garantia``: los que no les toca hasta que venza la garantía.
    * ``al_dia``: el resto (sin los próximos, que ya salen en ``por_hacer``).
    * ``conteos``: cuántos equipos hay en cada estado; los próximos cuentan
      como ``al_dia``.
    """
    hoy = hoy or timezone.localdate()
    limite = hoy + timedelta(days=DIAS_PROXIMOS)
    activos = list(activos_programables())

    frecuencias = dict(PlantillaChecklist.objects.values_list("tipo_dispositivo", "frecuencia_meses"))
    programadas = dict(
        ProgramacionMantenimiento.objects.filter(activo__in=activos).values_list("activo_id", "fecha_programada")
    )
    # Una sola lectura de las cerradas: la primera de cada equipo es su último
    # cierre y la primera que cuenta como preventivo completo, su ciclo.
    ultimos, completos = {}, {}
    for orden in _cerradas().filter(activo__in=activos).select_related("activo"):
        ultimos.setdefault(orden.activo_id, orden)
        if _es_preventivo_completo(orden):
            completos.setdefault(orden.activo_id, orden)

    por_hacer, en_garantia, al_dia = [], [], []
    conteos = {PROGRAMADO: 0, LE_TOCA: 0, EN_GARANTIA: 0, AL_DIA: 0}
    for activo in activos:
        s = _armar(
            activo,
            hoy,
            frecuencias.get(activo.tipo_dispositivo, FRECUENCIA_POR_DEFECTO),
            completos.get(activo.pk),
            ultimos.get(activo.pk),
            programadas.get(activo.pk),
        )
        conteos[s.estado] += 1
        if s.estado in (PROGRAMADO, LE_TOCA):
            por_hacer.append(s)
        elif s.estado == EN_GARANTIA:
            en_garantia.append(s)
        elif s.le_toca_desde <= limite:
            por_hacer.append(s)
        else:
            al_dia.append(s)

    por_hacer.sort(key=lambda s: (s.fecha_programada or s.le_toca_desde, s.activo.serial))
    en_garantia.sort(key=lambda s: (s.vencimiento_garantia, s.activo.serial))
    al_dia.sort(key=lambda s: (s.le_toca_desde, s.activo.serial))
    return {"por_hacer": por_hacer, "en_garantia": en_garantia, "al_dia": al_dia, "conteos": conteos}


def proximo_preventivo(orden):
    """Cuándo toca el siguiente preventivo, a partir de una orden cerrada.

    ``None`` si la orden no es un preventivo (o no tiene fecha de cierre). Si el
    preventivo se hizo en garantía, el siguiente toca al vencer la garantía.
    """
    if orden.tipo != "preventivo":
        return None
    if orden.en_garantia:
        return orden.activo.fecha_vencimiento_garantia
    if orden.fecha_cierre is None:
        return None
    return _add_months(orden.fecha_cierre, _frecuencia(orden.activo.tipo_dispositivo))
