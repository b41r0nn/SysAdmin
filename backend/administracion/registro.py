"""Lectura cacheada del catálogo de módulos y de la matriz de permisos.

``invalidar_cache`` es el único invalidador de configuración del proyecto: toda
clave de caché que dependa de la configuración editable se limpia aquí, para que
quien cambie algo no tenga que acordarse de cuál borrar.
"""

import logging

from django.core.cache import cache
from django.db import DatabaseError

from accounts.permisos import MODULOS, PERMISOS_POR_ROL

from .models import Modulo, PermisoRol, Rol

logger = logging.getLogger(__name__)

CLAVE_CACHE_MODULOS = "sysadmin:modulos_activos"
CLAVE_CACHE_CATALOGO = "sysadmin:catalogo_modulos"
CLAVE_CACHE_PERMISOS = "sysadmin:permisos"
CLAVE_CACHE_ROLES = "sysadmin:roles"

# Red de seguridad: la invalidación por señales cubre save() y delete(), pero un
# queryset.update() o un SQL directo no las dispara. Con la caché compartida
# entre workers (FileBasedCache en producción) un valor sin vencimiento quedaría
# viejo hasta el siguiente reinicio.
SEGUNDOS_CACHE = 300

CLAVES_CACHE = (
    CLAVE_CACHE_MODULOS,
    CLAVE_CACHE_CATALOGO,
    CLAVE_CACHE_PERMISOS,
    CLAVE_CACHE_ROLES,
)


def modulos_activos():
    """Devuelve el conjunto de claves de los módulos encendidos.

    Con la tabla vacía (base nueva o migración a medias) devuelve todos los
    módulos: la falta de datos no puede esconder la aplicación. Esa respuesta no
    se guarda en caché, para que sembrar las filas después surta efecto de
    inmediato.
    """
    activos = cache.get(CLAVE_CACHE_MODULOS)
    if activos is not None:
        return activos
    try:
        filas = list(Modulo.objects.values_list("clave", "activo"))
    except DatabaseError:
        # Tabla inexistente o base caída: que el login no se caiga por esto. Pero
        # es un fallo abierto (reactiva los módulos que el administrador apagó),
        # así que no puede pasar en silencio.
        logger.warning(
            "No se pudo leer el catálogo de módulos; se tratan todos como activos.",
            exc_info=True,
        )
        return set(MODULOS)
    if not filas:
        # Mismo fallo abierto que el except, por otra puerta: sin filas se
        # reactivan los módulos apagados, así que tampoco puede ser silencioso.
        logger.warning(
            "El catálogo de módulos está vacío; se tratan todos como activos."
        )
        return set(MODULOS)
    activos = {clave for clave, activo in filas if activo}
    cache.set(CLAVE_CACHE_MODULOS, activos, SEGUNDOS_CACHE)
    return activos


def modulo_esta_activo(clave):
    """``True`` si la clave es un módulo conocido y está encendido."""
    if clave not in MODULOS:
        return False
    return clave in modulos_activos()


def catalogo_modulos():
    """Módulos encendidos, en el orden del menú, con lo necesario para pintarlos.

    Devuelve una lista de ``{clave, nombre, icono, url_nombre}`` ordenada por
    ``Modulo.orden``. ``modulos_activos`` solo guarda claves; el menú necesita
    además el nombre, el icono y la URL, y leerlos de la base en cada request
    sería una consulta por página.

    Si no hay filas o la base falla devuelve una lista vacía: el menú se queda
    sin módulos, pero la página abre. Es un fallo cerrado (a diferencia de
    ``modulos_activos``) porque aquí no se concede ningún acceso, solo se
    pintan enlaces; aun así queda en el log, y la respuesta no se guarda en
    caché para que sembrar las filas después surta efecto de inmediato.
    """
    catalogo = cache.get(CLAVE_CACHE_CATALOGO)
    if catalogo is not None:
        return catalogo
    try:
        filas = list(
            Modulo.objects.order_by("orden", "nombre").values(
                "clave", "nombre", "icono", "url_nombre", "activo"
            )
        )
    except DatabaseError:
        logger.warning(
            "No se pudo leer el catálogo de módulos; el menú queda sin módulos.",
            exc_info=True,
        )
        return []
    if not filas:
        logger.warning("El catálogo de módulos está vacío; el menú queda sin módulos.")
        return []
    catalogo = [
        {campo: fila[campo] for campo in ("clave", "nombre", "icono", "url_nombre")}
        for fila in filas
        if fila["activo"]
    ]
    cache.set(CLAVE_CACHE_CATALOGO, catalogo, SEGUNDOS_CACHE)
    return catalogo


def _matriz_permisos():
    """Devuelve ``{rol: {modulo: nivel}}`` con toda la tabla, en una consulta.

    El menú pregunta nueve veces por request, así que se cachea la matriz
    completa y no celda por celda. Con la tabla vacía o la base caída se
    responde con la matriz del código: ambas respuestas son un fallo abierto
    (dan los permisos de fábrica), dejan traza en el log y no se cachean, para
    que sembrar las filas después surta efecto de inmediato.
    """
    matriz = cache.get(CLAVE_CACHE_PERMISOS)
    if matriz is not None:
        return matriz
    try:
        filas = list(PermisoRol.objects.values_list("rol__clave", "modulo", "nivel"))
    except DatabaseError:
        logger.warning(
            "No se pudo leer la matriz de permisos; se usa la del código.",
            exc_info=True,
        )
        return PERMISOS_POR_ROL
    if not filas:
        logger.warning(
            "La matriz de permisos está vacía; se usa la del código."
        )
        return PERMISOS_POR_ROL
    matriz = {}
    for clave_rol, modulo, nivel in filas:
        matriz.setdefault(clave_rol, {})[modulo] = nivel
    cache.set(CLAVE_CACHE_PERMISOS, matriz, SEGUNDOS_CACHE)
    return matriz


def nivel_de(rol, modulo):
    """Nivel que la tabla da a ese par rol/módulo; ``ninguno`` si no hay fila.

    No es el punto de lectura de permisos del proyecto: eso es
    ``accounts.permisos.nivel_permiso``, que además aplica el apagado de
    módulos y el privilegio del superadministrador.
    """
    return _matriz_permisos().get(rol, {}).get(modulo, "ninguno")


def roles_choices():
    """Parejas ``(clave, nombre)`` para los ``choices`` de ``CustomUser.rol``.

    Django evalúa un ``choices`` llamable también en los chequeos del sistema,
    que corren *antes* de ``migrate``: sobre una base sin la tabla esto tiene
    que responder, no reventar. El respaldo son los cuatro roles de fábrica.
    No se registra el fallo porque aquí no se concede ningún acceso (solo se
    pintan opciones) y ese mismo error de base ya deja traza en la matriz.
    """
    opciones = cache.get(CLAVE_CACHE_ROLES)
    if opciones is not None:
        return opciones
    try:
        opciones = list(Rol.objects.all().values_list("clave", "nombre"))
    except DatabaseError:
        return _roles_de_respaldo()
    if not opciones:
        return _roles_de_respaldo()
    cache.set(CLAVE_CACHE_ROLES, opciones, SEGUNDOS_CACHE)
    return opciones


def _roles_de_respaldo():
    # Import local: accounts.models usa el envoltorio de roles_choices como
    # choices, así que importarlo en la cabecera cerraría el ciclo.
    from accounts.models import CustomUser

    return list(CustomUser.ROL_CHOICES)


def invalidar_cache():
    """Borra todas las claves de caché de configuración del proyecto."""
    cache.delete_many(CLAVES_CACHE)
