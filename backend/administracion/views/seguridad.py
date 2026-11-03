from django.contrib import messages
from django.shortcuts import redirect, render

from accounts.permisos import requiere_permiso
from core.utils import get_client_ip

from ..auditoria import auditar_cambios
from ..forms_seguridad import SeguridadForm
from ..models import ConfiguracionSistema


@requiere_permiso("administracion", "escritura")
def seguridad(request):
    """Edita la política de seguridad: sesión, bloqueo y contraseñas.

    Lo que se guarda aquí gobierna el login de todo el mundo, así que la
    pantalla exige escritura (no solo lectura) y cada campo cambiado deja su
    renglón de auditoría. Ninguno de los cuatro valores es un secreto, así que
    el detalle registra el valor anterior y el nuevo.
    """
    config = ConfiguracionSistema.get_config()

    if request.method == "POST":
        form = SeguridadForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            auditar_cambios(request.user, form, ip=get_client_ip(request))
            messages.success(request, "Política de seguridad actualizada.")
            return redirect("administracion:seguridad")
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = SeguridadForm(instance=config)

    return render(request, "administracion/seguridad_form.html", {
        "form": form,
        "config": config,
    })
