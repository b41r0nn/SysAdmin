from django.shortcuts import render

from accounts.permisos import requiere_permiso


@requiere_permiso("administracion", "lectura")
def modulos(request):
    """Marcador: la pantalla real llega en su propia tarea."""
    return render(request, "administracion/en_construccion.html", {
        "titulo": "Módulos",
        "icono": "bi-grid-3x3-gap",
    })
