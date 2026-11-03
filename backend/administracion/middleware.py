"""Filtro de módulos apagados.

Un módulo apagado deja de existir: sus URLs responden 404, no una redirección,
y eso vale también para el superadministrador y para las páginas públicas del
módulo (por ejemplo el formulario de reporte de soporte).
"""

from django.http import Http404

from accounts.permisos import APP_A_MODULO

from .registro import modulo_esta_activo

# Apps que nunca se filtran, aunque algún día alguien las añada a APP_A_MODULO
# por error: sin ellas no hay login (``accounts``), ni portada (``core``), ni
# forma de entrar a /admin/ ni de ver los avisos. Si el 404 se comiera el login,
# nadie podría volver a encender un módulo.
APPS_SIEMPRE_ABIERTAS = {"admin", "accounts", "core", "notificaciones"}


class ModuloActivoMiddleware:
    """Responde 404 a las URLs de un módulo que el administrador apagó.

    Se resuelve en ``process_view`` y no en ``__call__`` porque
    ``request.resolver_match`` solo existe después de resolver la URL, y es de
    ahí de donde sale el ``app_name`` que se traduce a clave de módulo.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if match is None:
            return None
        app_name = match.app_name
        # Sin namespace (p. ej. /media/, que revisa su propio permiso) o con uno
        # que no es un módulo: el filtro no opina.
        if not app_name or app_name in APPS_SIEMPRE_ABIERTAS:
            return None
        modulo = APP_A_MODULO.get(app_name)
        if modulo is None:
            return None
        if not modulo_esta_activo(modulo):
            raise Http404
        return None
