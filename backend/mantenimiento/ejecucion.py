"""Ejecución de un preventivo: iniciarlo copiando el checklist y marcar sus puntos."""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    FORMATO_ACTUAL,
    LIMITE_OBS_PUNTO,
    RESULTADOS_PUNTO,
    ChecklistItem,
    OrdenMantenimiento,
    PlantillaChecklist,
)
from .services import snapshot_software_ocs

ESTADOS_ABIERTOS = ("abierta", "en_proceso")


def plantilla_para(activo):
    """Plantilla de checklist del tipo del equipo, o None si ese tipo no tiene."""
    return PlantillaChecklist.objects.filter(tipo_dispositivo=activo.tipo_dispositivo).first()


def esta_en_garantia(activo, hoy):
    """El vencimiento existe y no ha pasado. Sin vencimiento calculable: no."""
    vencimiento = activo.fecha_vencimiento_garantia
    return vencimiento is not None and hoy <= vencimiento


def iniciar_preventivo(activo, usuario, hoy: date | None = None):
    """Abre un preventivo en proceso con los puntos de la plantilla copiados."""
    hoy = hoy or timezone.localdate()
    if activo.estado == "dado_de_baja":
        raise ValidationError("El equipo está dado de baja.")
    plantilla = plantilla_para(activo)
    if plantilla is None:
        raise ValidationError("No hay checklist para este tipo de equipo.")
    en_garantia = esta_en_garantia(activo, hoy)

    with transaction.atomic():
        abierto = OrdenMantenimiento.objects.filter(
            activo=activo, tipo="preventivo", estado__in=ESTADOS_ABIERTOS
        ).exists()
        if abierto:
            raise ValidationError("Este equipo ya tiene un mantenimiento preventivo abierto.")

        software = [s["name"] for s in snapshot_software_ocs(activo) if s.get("name")]
        orden = OrdenMantenimiento.objects.create(
            activo=activo,
            tipo="preventivo",
            estado="en_proceso",
            fecha_apertura=hoy,
            formato=FORMATO_ACTUAL,
            en_garantia=en_garantia,
            software_snapshot=software,
        )
        puntos = plantilla.puntos.filter(activo=True)
        if en_garantia:
            puntos = puntos.filter(aplica_en_garantia=True)
        ChecklistItem.objects.bulk_create(
            ChecklistItem(
                orden=orden,
                seccion=p.seccion,
                descripcion=p.descripcion,
                posicion=p.posicion,
            )
            for p in puntos.order_by("posicion", "id")
        )
    return orden


def marcar_punto(item, resultado, observacion=""):
    """Guarda el resultado de un punto. Con falla, la observación es obligatoria."""
    orden = item.orden
    if orden is None or orden.estado not in ESTADOS_ABIERTOS:
        raise ValidationError("El mantenimiento ya está cerrado.")
    if resultado not in dict(RESULTADOS_PUNTO):
        raise ValidationError("Resultado no válido.")
    observacion = (observacion or "").strip()
    if len(observacion) > LIMITE_OBS_PUNTO:
        raise ValidationError(f"La observación no puede pasar de {LIMITE_OBS_PUNTO} caracteres.")
    if resultado == "falla" and not observacion:
        raise ValidationError("Explica la falla en la observación.")
    item.resultado = resultado
    item.observacion = observacion
    item.save(update_fields=["resultado", "observacion"])
    return item
