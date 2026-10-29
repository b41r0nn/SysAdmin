"""Lectura cacheada del catálogo de módulos.

``invalidar_cache`` es el único invalidador de configuración del proyecto: toda
clave de caché que dependa de la configuración editable se limpia aquí, para que
quien cambie algo no tenga que acordarse de cuál borrar.
"""

import logging

from django.core.cache import cache
from django.db import DatabaseError

from accounts.permisos import MODULOS

from .models import Modulo

logger = logging.getLogger(__name__)

CLAVE_CACHE_MODULOS = "sysadmin:modulos_activos"

# Red de seguridad: la invalidación por señales cubre save() y delete(), pero un
# queryset.update() o un SQL directo no las dispara. Con la caché compartida
# entre workers (FileBasedCache en producción) un valor sin vencimiento quedaría
# viejo hasta el siguiente reinicio.
SEGUNDOS_CACHE = 300

CLAVES_CACHE = (CLAVE_CACHE_MODULOS,)


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
        return set(MODULOS)
    activos = {clave for clave, activo in filas if activo}
    cache.set(CLAVE_CACHE_MODULOS, activos, SEGUNDOS_CACHE)
    return activos


def modulo_esta_activo(clave):
    """``True`` si la clave es un módulo conocido y está encendido."""
    if clave not in MODULOS:
        return False
    return clave in modulos_activos()


def invalidar_cache():
    """Borra todas las claves de caché de configuración del proyecto."""
    cache.delete_many(CLAVES_CACHE)
