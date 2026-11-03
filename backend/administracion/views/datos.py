from django.shortcuts import render

from accounts.permisos import requiere_permiso


@requiere_permiso("administracion", "lectura")
def datos(request):
    """Marcador: la pantalla real llega en su propia tarea."""
    return render(request, "administracion/en_construccion.html", {
        "titulo": "Datos",
        "icono": "bi-database",
    })
