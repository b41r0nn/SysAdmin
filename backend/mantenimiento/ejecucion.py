"""Ejecución de un mantenimiento: iniciar un preventivo copiando el checklist,
marcar sus puntos, cerrarlo (congelando los datos del acta) y reabrirlo."""

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    ESTADOS_FINALES,
    FORMATO_ACTUAL,
    LIMITE_OBS_PUNTO,
    LIMITE_TEXTO_ACTA,
    RESULTADOS_PUNTO,
    ChecklistItem,
    OrdenMantenimiento,
    PlantillaChecklist,
    ProgramacionMantenimiento,
)
from .programacion import proximo_preventivo
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


# ─── Cierre ──────────────────────────────────────────────────────────

VACIO = "—"
TIPOS_DE_COMPUTO = ("portatil", "escritorio")
TITULO_COMPUTO = "ACTA DE MANTENIMIENTO DE EQUIPOS DE CÓMPUTO"
TITULO_OTROS = "ACTA DE MANTENIMIENTO DE EQUIPOS"


def _texto(valor):
    return str(valor).strip() if valor is not None else ""


def _pulgadas(valor):
    """24.0 -> "24", 23.8 -> "23.8"; vacío si no hay dato."""
    if valor in (None, ""):
        return ""
    try:
        return format(Decimal(str(valor)).normalize(), "f")
    except InvalidOperation:
        return _texto(valor)


def _fecha(valor):
    return valor.strftime("%d/%m/%Y")


def campos_equipo(activo):
    """Datos del equipo que imprime el acta, como pares ``[etiqueta, valor]``.

    Son listas (no tuplas) porque se guardan en ``datos_acta`` (JSON). Un valor
    vacío se muestra como "—".
    """
    tipo = activo.tipo_dispositivo
    campos = [
        ("Equipo", activo.get_tipo_dispositivo_display()),
        ("Marca/modelo", f"{_texto(activo.marca)} {_texto(activo.modelo)}"),
        ("Serial", activo.serial),
        ("N° interno", activo.numero_interno),
    ]
    if tipo in TIPOS_DE_COMPUTO:
        campos += [
            ("Nombre", activo.nombre_equipo),
            ("Procesador", activo.procesador),
            ("RAM", activo.ram),
            ("Disco", f"{_texto(activo.disco_capacidad)} {_texto(activo.tipo_disco)}"),
            ("S.O.", activo.sistema_operativo),
            ("IP", activo.ip_equipo),
        ]
    elif tipo == "celular":
        campos += [
            ("IMEI", activo.imei),
            ("Línea", activo.numero_linea),
            ("Operador", activo.operador),
            ("Almacenamiento", activo.almacenamiento),
        ]
    elif tipo == "telefono_fijo":
        campos += [
            ("Extensión", activo.extension),
            ("Línea", activo.linea_asignada),
        ]
    elif tipo == "monitor":
        campos += [
            ("Pulgadas", _pulgadas(activo.pulgadas)),
            ("Resolución", activo.resolucion),
        ]
    campos.append(("Ubicación", activo.ubicacion_fisica))
    return [[etiqueta, _texto(valor) or VACIO] for etiqueta, valor in campos]


def _tipo_acta(orden):
    if orden.tipo == "correctivo":
        return "Correctivo"
    return "Preventivo en garantía" if orden.en_garantia else "Preventivo"


def _garantia(activo, fecha_cierre):
    vencimiento = activo.fecha_vencimiento_garantia
    if vencimiento is None:
        return "Sin dato"
    if fecha_cierre <= vencimiento:
        return f"Hasta {_fecha(vencimiento)}"
    return f"Vencida {_fecha(vencimiento)}"


def _responsable(activo):
    """El de la asignación activa, o None si el equipo no está asignado."""
    asignacion = activo.asignaciones.filter(activa=True).select_related("usuario").first()
    if asignacion is None:
        return None
    u = asignacion.usuario
    return {
        "nombre": u.nombre_completo,
        "documento": u.documento_identidad,
        "cargo": u.cargo,
        "area": u.area,
    }


def datos_para_acta(orden, usuario):
    """Todo lo que imprime el acta y no es parte de la orden, listo para congelar.

    Se llama con ``orden.fecha_cierre`` ya asignada; ``usuario`` es el técnico.
    """
    activo = orden.activo
    fecha_cierre = orden.fecha_cierre or timezone.localdate()
    proximo = proximo_preventivo(orden)
    return {
        "tipo_acta": _tipo_acta(orden),
        "titulo": TITULO_COMPUTO if activo.tipo_dispositivo in TIPOS_DE_COMPUTO else TITULO_OTROS,
        "campos": campos_equipo(activo),
        "garantia": _garantia(activo, fecha_cierre),
        "proximo": _fecha(proximo) if proximo else "",
        "responsable": _responsable(activo),
        "tecnico": {
            "nombre": usuario.get_full_name().strip() or usuario.get_username(),
            "cargo": usuario.cargo,
        },
    }


def errores_para_cerrar(
    orden, *, fecha_cierre, estado_final, observaciones, diagnostico="", acciones="", hoy: date | None = None
):
    """Lo que impide cerrar la orden, en el orden en que se muestra. Vacía: se puede cerrar.

    ``hoy`` es la fecha de hoy (por defecto, la local); existe para las pruebas.
    """
    if orden.estado == "cerrada":
        return ["El mantenimiento ya está cerrado."]
    hoy = hoy or timezone.localdate()
    errores = []
    if fecha_cierre is None:
        errores.append("Indica la fecha de cierre.")
    elif fecha_cierre > hoy:
        errores.append("La fecha de cierre no puede ser futura.")
    elif orden.fecha_apertura and fecha_cierre < orden.fecha_apertura:
        errores.append("La fecha de cierre no puede ser anterior a la apertura.")
    if estado_final not in dict(ESTADOS_FINALES):
        errores.append("Elige el estado final del equipo.")
    if len((observaciones or "").strip()) > LIMITE_TEXTO_ACTA:
        errores.append(f"Las observaciones no pueden pasar de {LIMITE_TEXTO_ACTA} caracteres.")

    if orden.tipo == "preventivo" and orden.formato == FORMATO_ACTUAL:
        items = list(orden.checklist_items.all())
        pendientes = sum(1 for i in items if not i.resultado)
        if pendientes:
            errores.append(f"Quedan puntos del checklist sin marcar ({pendientes}).")
        if any(i.resultado == "falla" and not i.observacion.strip() for i in items):
            errores.append("Cada falla necesita su observación.")
    elif orden.tipo == "correctivo":
        diagnostico = (diagnostico or "").strip()
        acciones = (acciones or "").strip()
        if not diagnostico:
            errores.append("Escribe el diagnóstico.")
        if not acciones:
            errores.append("Escribe la solución o las acciones realizadas.")
        if len(diagnostico) > LIMITE_TEXTO_ACTA:
            errores.append(f"El diagnóstico no puede pasar de {LIMITE_TEXTO_ACTA} caracteres.")
        if len(acciones) > LIMITE_TEXTO_ACTA:
            errores.append(f"La solución no puede pasar de {LIMITE_TEXTO_ACTA} caracteres.")
    return errores


def cerrar_orden(
    orden, usuario, *, fecha_cierre, estado_final, observaciones, diagnostico="", acciones="", hoy: date | None = None
):
    """Cierra la orden con ``usuario`` como técnico y congela los datos del acta.

    Lanza ``ValidationError`` con la lista de ``errores_para_cerrar``. Si es un
    preventivo, borra la fecha programada del equipo.
    """
    with transaction.atomic():
        # Se relee el estado con bloqueo: dos envíos seguidos no cierran dos veces.
        orden.estado = (
            OrdenMantenimiento.objects.select_for_update().values_list("estado", flat=True).get(pk=orden.pk)
        )
        errores = errores_para_cerrar(
            orden,
            fecha_cierre=fecha_cierre,
            estado_final=estado_final,
            observaciones=observaciones,
            diagnostico=diagnostico,
            acciones=acciones,
            hoy=hoy,
        )
        if errores:
            raise ValidationError(errores)

        orden.estado = "cerrada"
        orden.fecha_cierre = fecha_cierre
        orden.estado_final = estado_final
        orden.observaciones = (observaciones or "").strip()
        orden.tecnico = usuario
        campos = ["estado", "fecha_cierre", "estado_final", "observaciones", "tecnico", "datos_acta"]
        if orden.tipo == "correctivo":
            orden.diagnostico = (diagnostico or "").strip()
            orden.acciones = (acciones or "").strip()
            campos += ["diagnostico", "acciones"]
        orden.datos_acta = datos_para_acta(orden, usuario)
        orden.save(update_fields=[*campos, "fecha_actualizacion"])

        if orden.tipo == "preventivo":
            ProgramacionMantenimiento.objects.filter(activo_id=orden.activo_id).update(fecha_programada=None)


def reabrir_orden(orden):
    """Vuelve a poner la orden en proceso y descongela el acta.

    Un acta firmada ya subida se conserva, marcada como de una versión anterior.
    """
    if orden.estado != "cerrada":
        raise ValidationError("El mantenimiento no está cerrado.")
    orden.estado = "en_proceso"
    orden.fecha_cierre = None
    orden.datos_acta = {}
    if orden.acta_firmada:
        orden.acta_firmada_desactualizada = True
    orden.save(
        update_fields=["estado", "fecha_cierre", "datos_acta", "acta_firmada_desactualizada", "fecha_actualizacion"]
    )
