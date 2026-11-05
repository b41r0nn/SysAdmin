from functools import wraps
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

# La llave de repuesto del sistema: el rol que no se puede degradar. Si su
# columna de permisos se pudiera bajar, un descuido dejaría la configuración
# sin nadie que entre a arreglarla. La regla vive en tres sitios que tienen que
# decir lo mismo, y por eso la clave es una sola constante: aquí
# (``nivel_permiso`` se la concede), en ``administracion.models.PermisoRol.clean``
# (que no deja guardar otra cosa) y en ``administracion.views.roles`` (que no
# deja ni intentarlo).
ROL_SUPERADMIN = "superadmin"

MODULOS = [
    "usuarios",
    "inventario",
    "mantenimiento",
    "passwords",
    "reportes",
    "documentos",
    "administracion",
    "soporte",
    "licencias",
    "prestamos",
]

# Los módulos sin los que el sistema no se puede administrar. La otra mitad de
# la anti-meta 1 de la spec: igual que la concesión de ``ROL_SUPERADMIN``, esta
# propiedad NO depende de los datos.
#
# Es una CONSTANTE de código y no una lectura de
# ``Modulo.objects.filter(es_esencial=True)`` a propósito: si la lista saliera
# de la tabla, quien pueda apagar un módulo podría también bajar ese
# ``es_esencial`` y estaríamos donde empezamos. Son los cuatro que la migración
# ``0006_sembrar_modulos`` siembra con ``es_esencial=True``.
#
# ``administracion.registro.modulos_activos`` los fuerza como activos, así que
# ni un ``queryset.update()``, ni un ``bulk_create``, ni un fixture, ni un SQL
# directo pueden dejar la configuración inalcanzable: sin esto bastaba un
# ``Modulo.objects.filter(clave="administracion").update(activo=False)`` para
# que ``ModuloActivoMiddleware`` respondiera 404 a toda la configuración —
# también al superusuario de Django— sin vuelta por la web, porque ``Modulo``
# no está registrado en ``/admin/``.
#
# La columna ``es_esencial`` sigue mandando en la interfaz (el interruptor sale
# ``disabled``) y en ``Modulo.clean()``: que las dos fuentes no se separen lo
# vigila ``administracion.test_registro`` →
# ``test_la_constante_de_esenciales_no_se_separa_de_la_columna``.
MODULOS_ESENCIALES = frozenset({
    "inventario",
    "mantenimiento",
    "passwords",
    "administracion",
})

# app_name de la URL -> clave de módulo. Casi todas coinciden por nombre; las dos
# que no (reports y yule) se mapean a mano.
APP_A_MODULO = {
    "usuarios": "usuarios",
    "inventario": "inventario",
    "mantenimiento": "mantenimiento",
    "passwords": "passwords",
    "reportes": "reportes",
    "documentos": "documentos",
    "administracion": "administracion",
    "soporte": "soporte",
    "licencias": "licencias",
    "prestamos": "prestamos",
    "reports": "reportes",
    "yule": "inventario",
}

# Matriz de fábrica. La fuente de verdad es la tabla administracion.PermisoRol,
# que la migración de datos siembra con exactamente esto; aquí se conserva como
# respaldo para una base vacía o caída. Nadie la lee fuera de este módulo: lo
# vigila administracion.test_roles.PuntoUnicoDeLecturaTests.
PERMISOS_POR_ROL = {
    "superadmin": {m: "escritura" for m in MODULOS},
    "admin": {
        "usuarios": "escritura",
        "inventario": "escritura",
        "mantenimiento": "escritura",
        "passwords": "lectura",
        "reportes": "escritura",
        "documentos": "escritura",
        "administracion": "ninguno",
        "soporte": "escritura",
        "licencias": "escritura",
        "prestamos": "escritura",
    },
    "tecnico": {
        "usuarios": "lectura",
        "inventario": "escritura",
        "mantenimiento": "escritura",
        "passwords": "ninguno",
        "reportes": "lectura",
        "documentos": "lectura",
        "administracion": "ninguno",
        "soporte": "escritura",
        "licencias": "lectura",
        "prestamos": "escritura",
    },
    "lectura": {m: "lectura" for m in MODULOS if m != "administracion"}
    | {"administracion": "ninguno"},
}


# Roles que pueden ver secretos de la bóveda en claro. El permiso "lectura" del
# módulo passwords solo da acceso al listado (títulos, usuarios, URLs).
ROLES_VER_SECRETOS = {"superadmin", "admin"}


def nivel_permiso(rol: str, modulo: str) -> str:
    """Único punto de lectura de permisos. Orden de las reglas, que importa:
    un módulo inactivo gana sobre superadmin (así Licencias desaparece también
    para el superadministrador), y superadmin gana sobre la tabla."""
    # Import local: administracion.models importa MODULOS de este módulo, así
    # que un import en la cabecera cerraría el ciclo al cargar las apps. Es el
    # patrón de inventario.services.
    from administracion.registro import modulo_esta_activo, nivel_de

    if not modulo_esta_activo(modulo):
        return "ninguno"
    if rol == ROL_SUPERADMIN:
        return "escritura"
    return nivel_de(rol, modulo)


def administracion_roles_choices():
    """``choices`` de ``CustomUser.rol``: los roles que haya en la tabla.

    Envoltorio de ``administracion.registro.roles_choices``. Vive aquí para que
    ``accounts/models.py`` no tenga que importar ``administracion``.
    """
    from administracion.registro import roles_choices

    return roles_choices()


def puede_ver_secretos(user):
    """True si el usuario puede revelar secretos de la bóveda."""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or getattr(user, "rol", None) in ROLES_VER_SECRETOS


def tiene_permiso(user, modulo, nivel="lectura"):
    """True si el usuario tiene al menos `nivel` en `modulo`."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    permiso = nivel_permiso(getattr(user, "rol", ""), modulo)
    if permiso == "ninguno":
        return False
    return nivel != "escritura" or permiso == "escritura"


MENSAJE_SIN_PERMISO = "No tienes permiso para acceder a esta sección."

# Cuerpo del 403 que reciben las peticiones de HTMX. Se muestra tal cual: el
# manejador de ``htmx:responseError`` de ``static/js/sysadmin.js`` lo pinta como
# aviso en pantalla, así que va en español y no distingue entre las dos causas
# (ni hace falta: la salida es la misma).
MENSAJE_HTMX_SIN_PERMISO = (
    "No se pudo completar la acción: no tienes permiso o tu sesión caducó. "
    "Vuelve a entrar y reinténtalo; nada se guardó."
)


def requiere_permiso(modulo, nivel="lectura"):
    """
    Decorator que verifica permisos por rol.

    Args:
        modulo: clave de módulo (ej. "inventario", "passwords")
        nivel: "lectura" permite lectura y escritura; "escritura" exige escritura

    Una navegación normal sin permiso sigue viendo el mensaje y la redirección
    al tablero. Una petición de **HTMX** recibe 403, porque HTMX sigue un 302 de
    forma transparente y acabaría intercambiando el HTML completo del tablero
    —o del formulario de login— dentro del ``<tr>`` o el ``<td>`` que disparó la
    petición. ``django_htmx.middleware.HtmxMiddleware`` está en ``MIDDLEWARE``,
    así que ``request.htmx`` es lo que distingue una de otra.
    """

    def decorador(vista):
        @login_required
        def con_sesion(request, *args, **kwargs):
            if not tiene_permiso(request.user, modulo, nivel):
                messages.error(request, MENSAJE_SIN_PERMISO)
                return redirect("core:dashboard")
            return vista(request, *args, **kwargs)

        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            # El 403 se decide AQUÍ, fuera de ``login_required``, y no es un
            # detalle de estilo: ``login_required`` envuelve a ``con_sesion``,
            # así que corre ANTES de su cuerpo. El caso de la sesión caducada
            # —el disparador universal, y el más probable— lo redirige él al
            # formulario de login y nunca llega a la rama de permisos. Un 403
            # puesto solo ahí dentro dejaría el bug principal abierto.
            if getattr(request, "htmx", False) and not tiene_permiso(
                getattr(request, "user", None), modulo, nivel
            ):
                return HttpResponseForbidden(
                    MENSAJE_HTMX_SIN_PERMISO, content_type="text/plain; charset=utf-8"
                )
            return con_sesion(request, *args, **kwargs)

        return envoltura

    return decorador


def solo_superadmin(vista):
    """Shortcut: solo usuarios con rol=superadmin."""
    return requiere_permiso("administracion", "escritura")(vista)
