from django.contrib import messages
from django.shortcuts import redirect, render

from accounts.permisos import requiere_permiso
from core.utils import get_client_ip

from ..auditoria import auditar_cambios
from ..forms import ConfiguracionForm
from ..models import ConfiguracionSistema


@requiere_permiso("administracion", "escritura")
def configuracion(request):
    """Datos de la empresa y metadatos del acta.

    Cada campo cambiado deja su renglón de auditoría: el nombre de la empresa y
    la firma salen en todas las actas y los reportes, así que quién los cambió
    merece el mismo rastro que el resto de la configuración. Ninguno es un
    secreto, de modo que el detalle registra el valor anterior y el nuevo.
    """
    config = ConfiguracionSistema.get_config()

    if request.method == "POST":
        form = ConfiguracionForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            auditar_cambios(request.user, form, ip=get_client_ip(request))
            messages.success(request, "Configuración del sistema actualizada.")
            return redirect("administracion:configuracion")
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = ConfiguracionForm(instance=config)

    return render(request, "administracion/configuracion_form.html", {
        "form": form,
        "config": config,
    })
