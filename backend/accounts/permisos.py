from functools import wraps
from django.contrib import messages
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


def requiere_permiso(modulo, nivel="lectura"):
    """
    Decorator que verifica permisos por rol.

    Args:
        modulo: clave de módulo (ej. "inventario", "passwords")
        nivel: "lectura" permite lectura y escritura; "escritura" exige escritura
    """

    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            if request.user.is_superuser:
                return vista(request, *args, **kwargs)
            permiso = nivel_permiso(request.user.rol, modulo)
            if permiso == "ninguno" or (nivel == "escritura" and permiso != "escritura"):
                messages.error(request, "No tienes permiso para acceder a esta sección.")
                return redirect("core:dashboard")
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


def solo_superadmin(vista):
    """Shortcut: solo usuarios con rol=superadmin."""
    return requiere_permiso("administracion", "escritura")(vista)
