from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from accounts.permisos import requiere_permiso
from core.utils import get_client_ip

from ..models import Modulo
from ..services import registrar_auditoria


@requiere_permiso("administracion", "lectura")
def modulos(request):
    """Lista los módulos con un interruptor para encender o apagar cada uno."""
    return render(request, "administracion/modulos_lista.html", {
        "modulos": Modulo.objects.all(),
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
    return render(request, "administracion/partials/fila_modulo.html", {"modulo": modulo})
