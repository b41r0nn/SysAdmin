from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

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


def requiere_permiso(modulo, nivel="lectura"):
    """
    Decorator que verifica permisos por rol.

    Args:
        modulo: clave en PERMISOS_POR_ROL (ej. "inventario", "passwords")
        nivel: "lectura" permite lectura y escritura; "escritura" exige escritura
    """

    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            if request.user.is_superuser:
                return vista(request, *args, **kwargs)
            permiso = PERMISOS_POR_ROL.get(request.user.rol, {}).get(modulo, "ninguno")
            if permiso == "ninguno" or (nivel == "escritura" and permiso != "escritura"):
                messages.error(request, "No tienes permiso para acceder a esta sección.")
                return redirect("core:dashboard")
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


def solo_superadmin(vista):
    """Shortcut: solo usuarios con rol=superadmin."""
    return requiere_permiso("administracion", "escritura")(vista)