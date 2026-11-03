from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from accounts.permisos import requiere_permiso, tiene_permiso
from core.utils import get_client_ip

from ..models import Modulo
from ..services import registrar_auditoria


@requiere_permiso("administracion", "lectura")
def modulos(request):
    """Lista los módulos con un interruptor para encender o apagar cada uno.

    A quien solo tiene lectura no se le pinta el interruptor: la vista del POST
    exige escritura y responde 403, con el que HTMX no intercambia nada, así que
    el control se quedaría mostrando un valor que nadie guardó. Más vale que no
    esté.
    """
    return render(request, "administracion/modulos_lista.html", {
        "modulos": Modulo.objects.all(),
        "puede_escribir": tiene_permiso(request.user, "administracion", "escritura"),
    })


@requiere_permiso("administracion", "escritura")
@require_POST
def toggle_modulo(request, clave):
    """Invierte ``activo`` y devuelve la fila para que HTMX la reemplace."""
    modulo = get_object_or_404(Modulo, clave=clave)
    if modulo.es_esencial:
        # La casilla deshabilitada del HTML no es una validación.
        return HttpResponseBadRequest(
            f"El módulo «{modulo.nombre}» es esencial y no se puede desactivar."
        )
    modulo.activo = not modulo.activo
    try:
        # Por instancia y no con update(): así corren full_clean() y las señales
        # que invalidan la caché.
        modulo.save()
    except ValidationError as error:
        return HttpResponseBadRequest(" ".join(error.messages))
    registrar_auditoria(
        request.user,
        "administracion",
        "configurar",
        objeto=modulo,
        detalle=f"Módulo «{modulo.nombre}»: {'desactivado' if not modulo.activo else 'activado'}",
        ip=get_client_ip(request),
    )
    # ``puede_escribir`` va fijo: aquí solo llega quien tiene escritura (lo
    # exige el decorador). El parcial se pinta fuera del contexto de la
    # pantalla, así que sin pasárselo el intercambio devolvería la fila sin su
    # interruptor.
    return render(request, "administracion/partials/fila_modulo.html", {
        "modulo": modulo,
        "puede_escribir": True,
    })
