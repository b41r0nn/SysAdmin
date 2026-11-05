"""Middlewares del módulo de administración.

- ``ModuloActivoMiddleware``: filtro de módulos apagados. Un módulo apagado
  deja de existir: sus URLs responden 404, no una redirección, y eso vale
  también para el superadministrador y para las páginas públicas del módulo
  (por ejemplo el formulario de reporte de soporte).
- ``SesionConfigurableMiddleware``: vencimiento de la sesión según la
  configuración guardada.
"""

from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from accounts.permisos import APP_A_MODULO

from .registro import modulo_esta_activo
from .seguridad import minutos_de_sesion

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


class SesionConfigurableMiddleware(MiddlewareMixin):
    """Fija el vencimiento de la sesión con los minutos de la configuración.

    Se resuelve en ``process_request`` y va registrado después de
    ``AuthenticationMiddleware``, porque hace falta ``request.user`` para saber
    si hay una sesión que vencer.

    Hereda de ``MiddlewareMixin`` —como el propio ``AuthenticationMiddleware``
    de Django— y no es decorativo: de los hooks antiguos, un middleware de
    estilo nuevo solo honra ``process_view``, ``process_exception`` y
    ``process_template_response``. Un ``process_request`` en una clase sin el
    mixin **no se llama nunca**, y el síntoma sería que todo el mundo sigue con
    el vencimiento viejo sin que nada falle a la vista. Por eso
    ``ModuloActivoMiddleware``, aquí arriba, usa ``process_view``.

    ``SESSION_SAVE_EVERY_REQUEST`` ya está activo, así que el minutero se
    renueva en cada petición: lo que se cuenta es inactividad real y no tiempo
    desde el login.
    """

    def process_request(self, request):
        usuario = getattr(request, "user", None)
        if usuario is None or not usuario.is_authenticated:
            # Una sesión anónima no se toca: set_expiry() la marcaría como
            # modificada y la escribiría sin necesidad.
            return None
        request.session.set_expiry(minutos_de_sesion() * 60)
        return None
