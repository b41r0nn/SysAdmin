from django.shortcuts import render

from accounts.permisos import requiere_permiso


@requiere_permiso("administracion", "lectura")
def roles(request):
    """Marcador: la pantalla real llega en su propia tarea."""
    return render(request, "administracion/en_construccion.html", {
        "titulo": "Roles y permisos",
        "icono": "bi-shield-check",
    })
