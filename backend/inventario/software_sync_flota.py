"""Lectura periódica del software de todos los activos vinculados a OCS.

Corre el mismo `aplicar_reporte` que el botón "Leer de OCS", pero para toda la
flota y con los errores aislados: un equipo que no responde se registra como
fallo y el recorrido sigue con el siguiente. Si un corte de OCS tumbara el
sincronizado entero, la base quedaría con el inventario a medias y no habría
manera de saber en qué activo se cortó.

A diferencia de `sincronizar_equipos_ocs()`, esto **no** pide toda la flota a
OCS de una vez: son 121 filas por equipo, así que son N requests. Es lo que hace
`get_software()` por activo, y por eso conviene espaciar las vueltas.
"""
import logging
import time
from typing import Any, Dict, List, Optional

from django.utils import timezone

from mantenimiento.services import detalle_snapshot_software_ocs

from .models import Activo, SoftwareInstalado
from .software_sync import aplicar_reporte

logger = logging.getLogger(__name__)


def activos_con_equipo_ocs(incluir_dados_de_baja: bool = False):
    """Activos que tienen un equipo OCS vinculado y del que vale la pena leer."""
    consulta = Activo.objects.filter(equipo_ocs__isnull=False).distinct()
    if not incluir_dados_de_baja:
        consulta = consulta.exclude(estado="dado_de_baja")
    return consulta.order_by("pk")


def sincronizar_software(
    activos: Optional[List[Activo]] = None,
    dry_run: bool = False,
    on_equipo=None,
    pausa: float = 0.0,
) -> Dict[str, Any]:
    """Lee el software de cada activo y guarda solo las diferencias.

    Args:
        activos: a qué activos leerle. Por defecto, todos los que estén
            vinculados a un equipo OCS y no estén dados de baja.
        dry_run: no escribe nada, solo consulta OCS y reporta qué encontró.
        on_equipo: callback con la lista de detalle, para ir mostrando avance.
        pausa: segundos de espera entre equipo y equipo. Son N requests
            seguidos contra un servidor interno; sin pausa una vuelta completa
            se lee como un barrido.

    Returns:
        dict con el resumen de la vuelta: leidos, con_cambios, fallidos, y el
        detalle de cada equipo para poder diagnosticar sin releer todo.
    """
    if activos is None:
        activos = list(activos_con_equipo_ocs())

    resumen = {
        "iniciada": timezone.now(),
        "leidos": 0,
        "con_cambios": 0,
        "fallidos": 0,
        "nuevos": 0,
        "actualizados": 0,
        "desinstalados": 0,
        "reinstalados": 0,
        "coexistencia": 0,
        "guardadas": 0,
        "detalle": [],
    }

    for indice, activo in enumerate(activos):
        if pausa and indice:
            time.sleep(pausa)

        equipo = activo.equipo_ocs.first()
        nombre = equipo.nombre_host if equipo else "?"
        info = detalle_snapshot_software_ocs(activo)


        if info["estado"] != "ok":
            # Sin reporte no se toca la base (ver software_sync). Cuenta como
            # leído igual, para que el log diga la verdad sobre qué se intentó.
            resumen["leidos"] += 1
            if info["estado"] == "error":
                resumen["fallidos"] += 1
            logger.info("Software %s (%s): %s", activo.serial, nombre, info["estado"])
            resumen["detalle"].append({
                "activo": activo.serial,
                "host": nombre,
                "estado": info["estado"],
                "cambios": 0,
                "programas": 0,
            })
        elif dry_run:
            # Sin escribir no hay diff que mostrar, así que se reporta lo que
            # traería el reporte y lo contrasta con lo que ya está guardado.
            guardado = SoftwareInstalado.objects.filter(activo=activo, presente=True).count()
            resumen["leidos"] += 1
            resumen["detalle"].append({
                "activo": activo.serial,
                "host": nombre,
                "estado": "ok",
                "cambios": 0,
                "programas": len(info["software"]),
                "guardadas": guardado,
            })
        else:
            cambios = aplicar_reporte(activo, info["software"])
            resumen["leidos"] += 1
            for clave in ("nuevos", "actualizados", "desinstalados", "reinstalados", "coexistencia"):
                resumen[clave] += cambios[clave]
            total = (
                cambios["nuevos"] + cambios["actualizados"] + cambios["desinstalados"]
                + cambios["reinstalados"] + cambios["coexistencia"]
            )
            if total:
                resumen["con_cambios"] += 1
            resumen["detalle"].append({
                "activo": activo.serial,
                "host": nombre,
                "estado": "ok",
                "cambios": total,
                "programas": len(info["software"]),
                "nuevos": cambios["nuevos"],
                "desinstalados": cambios["desinstalados"],
                "reinstalados": cambios["reinstalados"],
            })

        if on_equipo is not None:
            on_equipo(resumen["detalle"])

    resumen["terminada"] = timezone.now()
    resumen["duracion_segundos"] = int(
        (resumen["terminada"] - resumen["iniciada"]).total_seconds()
    )
    resumen["guardadas"] = SoftwareInstalado.objects.count()
    return resumen


def linea_resumen(resumen: Dict[str, Any]) -> str:
    """El resumen en una línea, para el log y para los mensajes de la vista."""
    if resumen["fallidos"]:
        return (
            f"{resumen['leidos']} activos leídos, {resumen['con_cambios']} con cambios, "
            f"{resumen['fallidos']} sin respuesta de OCS "
            f"(+{resumen['nuevos']} nuevos, -{resumen['desinstalados']} desinstalados, "
            f"{resumen['reinstalados']} reinstalados) en {resumen['duracion_segundos']}s"
        )
    return (
        f"{resumen['leidos']} activos leídos, {resumen['con_cambios']} con cambios "
        f"(+{resumen['nuevos']} nuevos, -{resumen['desinstalados']} desinstalados, "
        f"{resumen['reinstalados']} reinstalados) en {resumen['duracion_segundos']}s"
    )
