"""Sincronización del inventario de software de un activo con la BD local.

El reporte de OCS llega completo cada vez (en W11F35F son 122 programas). Aquí
se compara contra lo que ya está guardado y **solo se escriben las diferencias**,
que es lo que hace que la tabla sirva: no se borra y se reescribe el equipo
entero en cada vuelta.

Regla que gobierna todo el módulo: los faltantes (bajas) **solo** se calculan si
el reporte llegó de verdad. Si OCS no respondió, o el equipo no está vinculado, o
el agente no reportó, no se toca una sola fila. Confundir "desinstaló" con "no
reportó" haría que un equipo apagado el fin de semana apareciera con el
inventario vacío y al lunes "reinstallara" 122 programas.
"""
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from mantenimiento.services import detalle_snapshot_software_ocs

from .models import SoftwareInstalado

logger = logging.getLogger(__name__)


#: OCS devuelve esta cadena literal cuando el agente no reporta el dato. Si se
#: guardara tal cual, un programa whose versión a veces no llega pase de "" a
#: "Unavailable" y vice versa se registraría como si fuera un cambio de versión.
SIN_DATO = "unavailable"


def _limpiar(valor: Any) -> str:
    texto = str(valor or "").strip()
    return "" if texto.lower() == SIN_DATO else texto


def normalizar_reporte(software_ocs: Iterable[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    """Convierte el reporte de OCS en la forma que se guarda.

    Quita duplicados exactos y descarta entradas sin nombre: un producto vacío no
    es un programa y ensuciaría el histórico.
    """
    vistos = {}
    for item in software_ocs or []:
        if not isinstance(item, dict):
            continue
        nombre = _limpiar(item.get("name"))
        if not nombre:
            continue
        version = _limpiar(item.get("version"))
        fabricante = _limpiar(item.get("publisher"))
        vistos.setdefault((nombre, version), fabricante)
    return [(n, v, f) for (n, v), f in vistos.items()]


@transaction.atomic
def aplicar_reporte(
    activo,
    software_ocs: Iterable[Dict[str, Any]],
    ahora=None,
) -> Dict[str, int]:
    """Compara el reporte de OCS con lo guardado y escribe solo los cambios.

    No llama a OCS ni debe usarse sin un reporte en la mano: si no hay reporte,
    la respuesta correcta es no hacer nada.

    El cruce se hace por (nombre, versión) pero con un caso especial: un nombre
    reportado sin versión no genera una fila nueva ni da de baja las que hubiera.
    OCS responde "Unavailable" cuando el agente deja de informar el campo, y
    tratarlo como versión vacía haría que en cada vuelta el programa apareciera
    como versión nueva y la anterior como desinstalada. Perdimos el dato, no el
    programa: se conservan las filas que ya existen.

    Args:
        activo: Activo cuyo inventario se actualiza.
        software_ocs: filas tal como las devuelve `get_software`.
        ahora: momento del reporte; se usa para no tener que fijar el reloj en
            las pruebas.

    Returns:
        dict con el conteo de cada tipo de cambio:
        nuevos, actualizados, desinstalados, reinstalados, coexistencia, sin_cambios
    """
    ahora = ahora or timezone.now()
    reporte = normalizar_reporte(software_ocs)
    claves_reporte = {(nombre, version) for nombre, version, _ in reporte}
    ids_vistos = set()

    existentes = list(SoftwareInstalado.objects.filter(activo=activo))
    por_clave = {(f.nombre, f.version): f for f in existentes}
    # Nombres cuyo reporte vino sin versión: no se tocan sus filas.
    sin_version = {nombre for nombre, version, _ in reporte if not version}
    ids_sin_version = {f.pk for f in existentes if f.nombre in sin_version}

    nuevas: List[SoftwareInstalado] = []
    resumen = {
        "nuevos": 0,
        "actualizados": 0,
        "desinstalados": 0,
        "reinstalados": 0,
        "coexistencia": 0,
        "sin_cambios": 0,
    }

    for nombre, version, fabricante in reporte:
        if not version and any(f.nombre == nombre for f in existentes):
            # Ya conocemos el programa; el reporte solo no trajo la versión.
            ids_vistos.update(f.pk for f in existentes if f.nombre == nombre)
            ids_vistos.update(ids_sin_version)
            resumen["sin_cambios"] += 1
            continue

        fila = por_clave.get((nombre, version))
        if fila is None:
            # ¿Es un programa nuevo, un reemplazo de versión o una coexistencia?
            # La diferencia está en si la otra versión sigue apareciendo en este
            # mismo reporte: Windows instala runtimes de 32 y 64 bits del mismo
            # nombre a la vez, así que si el reporte trae las dos no hubo cambio,
            # y si trae solo la nueva, la anterior quedó reemplazada.
            otras = [
                f
                for f in existentes
                if f.nombre == nombre and f.version != version and f.presente
            ]
            siguen_reportadas = any((f.nombre, f.version) in claves_reporte for f in otras)
            coexiste = bool(otras) and siguen_reportadas
            nuevas.append(
                SoftwareInstalado(
                    activo=activo,
                    nombre=nombre,
                    version=version,
                    fabricante=fabricante,
                    fecha_instalacion=ahora,
                    fecha_ultima_vista=ahora,
                    presente=True,
                )
            )
            if coexiste:
                resumen["coexistencia"] += 1
            else:
                resumen["nuevos"] += 1
            continue

        if fila.presente:
            ids_vistos.add(fila.pk)
            if fila.fabricante != fabricante and fabricante:
                fila.fabricante = fabricante
                fila.fecha_ultima_vista = ahora
                fila.save(update_fields=["fabricante", "fecha_ultima_vista"])
                resumen["actualizados"] += 1
            else:
                # Sin cambios: ni se escribe. Una fila por programa por vuelta
                # convertiría 122 updates por equipo y hora en 3.000 filas/sync
                # de historial inútil.
                resumen["sin_cambios"] += 1
        else:
            # Estaba dado de baja y volvió. La fecha de instalación se refresca
            # porque la pregunta que responde ("¿cuándo se instaló esto en este
            # equipo?") es la de la última instalación, no la de la primera vez
            # que lo vimos.
            fila.presente = True
            fila.fecha_retiro = None
            fila.fecha_instalacion = ahora
            fila.fecha_ultima_vista = ahora
            if fabricante:
                fila.fabricante = fabricante
            fila.save(
                update_fields=[
                    "presente",
                    "fecha_retiro",
                    "fecha_instalacion",
                    "fecha_ultima_vista",
                    "fabricante",
                ]
            )
            ids_vistos.add(fila.pk)
            resumen["reinstalados"] += 1

    if nuevas:
        SoftwareInstalado.objects.bulk_create(nuevas)
        ids_vistos.update(f.pk for f in nuevas)

    # Bajas: presentes en la BD que el reporte ya no menciona.
    for fila in existentes:
        if fila.presente and fila.pk not in ids_vistos:
            fila.presente = False
            fila.fecha_retiro = ahora
            fila.fecha_ultima_vista = ahora
            fila.save(update_fields=["presente", "fecha_retiro", "fecha_ultima_vista"])
            resumen["desinstalados"] += 1

    total = (
        resumen["nuevos"]
        + resumen["actualizados"]
        + resumen["desinstalados"]
        + resumen["reinstalados"]
        + resumen["coexistencia"]
    )
    if total:
        logger.info(
            "Software %s: %s nuevos, %s actualizados, %s desinstalados, "
            "%s reinstalados, %s versiones coexistiendo",
            activo.serial,
            resumen["nuevos"],
            resumen["actualizados"],
            resumen["desinstalados"],
            resumen["reinstalados"],
            resumen["coexistencia"],
        )
    return resumen


def refrescar_activo(activo) -> Dict[str, Any]:
    """Pide el software a OCS y, solo si llegó, actualiza la BD local.

    Devuelve el mismo dict que `detalle_snapshot_software_ocs` más `resumen`,
    para que la vista pueda mostrar los estados de error con los mismos textos.
    """
    info = detalle_snapshot_software_ocs(activo)
    if info["estado"] != "ok":
        # Sin reporte no se toca la BD: ver la nota del módulo.
        return {**info, "resumen": None}

    resumen = aplicar_reporte(activo, info["software"])
    return {**info, "resumen": resumen}


def software_guardado(activo, solo_presentes: bool = True):
    """Filas de software de un activo, ordenadas como las muestra la vista."""
    consulta = SoftwareInstalado.objects.filter(activo=activo)
    if solo_presentes:
        consulta = consulta.filter(presente=True)
    return consulta.order_by("nombre", "version")


def ultimo_reporte(activo) -> Optional[Any]:
    """Momento en que OCS confirmó por última vez el software del activo."""
    return (
        SoftwareInstalado.objects.filter(activo=activo)
        .order_by("-fecha_ultima_vista")
        .values_list("fecha_ultima_vista", flat=True)
        .first()
    )
