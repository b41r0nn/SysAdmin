from django.contrib import messages
from django.shortcuts import redirect, render

from accounts.permisos import requiere_permiso

from ..forms import ConfiguracionForm
from ..models import ConfiguracionSistema


@requiere_permiso("administracion", "escritura")
def configuracion(request):
    config = ConfiguracionSistema.get_config()

    if request.method == "POST":
        form = ConfiguracionForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuración del sistema actualizada.")
            return redirect("administracion:configuracion")
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = ConfiguracionForm(instance=config)

    return render(request, "administracion/configuracion_form.html", {
        "form": form,
        "config": config,
    })
