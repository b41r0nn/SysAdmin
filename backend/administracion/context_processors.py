"""Datos que toda plantilla recibe sin que la vista los pase.

``menu_modulos`` alimenta el menú lateral de ``base.html``: el catálogo de
módulos encendidos, filtrado por lo que el rol del usuario puede ver.
"""

import logging

from django.urls import NoReverseMatch, reverse
from django.utils.functional import SimpleLazyObject

from accounts.permisos import nivel_permiso

from .registro import catalogo_modulos

logger = logging.getLogger(__name__)


def menu_modulos(request):
    """Opciones del menú lateral, en el orden de ``Modulo.orden``.

    ``menu_modulos`` es una lista de ``{clave, nombre, icono, url, activo}``;
    ``activo`` marca la sección que el usuario tiene abierta (es la clase
    ``active`` del enlace, no si el módulo está encendido: los apagados ni
    llegan a la lista). Sin sesión no hay menú.

    La lista es perezosa: el procesador corre en cada ``render(request, ...)``,
    también en los fragmentos HTMX y en las páginas de ``/admin/``, y solo la
    plantilla de la que cuelga el menú la recorre.
    """
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {}
    return {"menu_modulos": SimpleLazyObject(lambda: _opciones(request, usuario))}


def _opciones(request, usuario):
    rol = getattr(usuario, "rol", "")
    seccion = getattr(getattr(request, "resolver_match", None), "app_name", "")
    opciones = []
    for modulo in catalogo_modulos():
        # El único punto de lectura de permisos: además de la matriz aplica el
        # apagado del módulo y el privilegio del superadministrador.
        if nivel_permiso(rol, modulo["clave"]) == "ninguno":
            continue
        try:
            url = reverse(modulo["url_nombre"])
        except NoReverseMatch:
            # Una fila mal escrita no puede dar 500 en todas las páginas, ni
            # siquiera para el superadministrador que tendría que arreglarla.
            logger.warning(
                "El módulo «%s» apunta a la URL «%s», que no existe; se omite del menú.",
                modulo["clave"],
                modulo["url_nombre"],
                exc_info=True,
            )
            continue
        # El namespace de la URL es el app_name de las vistas del módulo:
        # reports:index -> reports, aunque la clave del módulo sea reportes.
        namespace, separador, _ = modulo["url_nombre"].partition(":")
        opciones.append(
            {
                "clave": modulo["clave"],
                "nombre": modulo["nombre"],
                "icono": modulo["icono"],
                "url": url,
                "activo": bool(separador) and namespace == seccion,
            }
        )
    return opciones
