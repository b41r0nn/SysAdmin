"""Pantalla de Datos: cuánto historial se guarda y qué borraría la limpieza.

Dos decisiones gobiernan este módulo:

- **La simulación no barre el disco de media.** Llama al comando con
  ``--dry-run`` y además con ``--sin-media``, porque
  ``_limpiar_media_huerfana()`` hace un ``os.walk`` sobre ``MEDIA_ROOT`` y un
  ``getmtime`` por archivo también en modo simulación: lo único que se salta es
  el ``os.remove``. Eso es el disco entero de media dentro de una petición HTTP,
  sin cota de archivos ni tiempo máximo, y el trabajador de gunicorn que la
  atiende tiene un ``GUNICORN_TIMEOUT``. Es el mismo defecto que obligó a
  ponerle ``timeout`` al SMTP cuando la pantalla de Correo pasó a llamar desde
  una petición algo que antes solo llamaba el cron. Lo que se pierde —un número
  de archivos huérfanos— no cambia ninguna decisión del administrador, que aquí
  decide plazos; el barrido real lo sigue haciendo la tarea programada y la
  pantalla lo dice.

- **La simulación se audita con ``registrar_auditoria``**, no con
  ``auditar_cambios``: no hay formulario ni campos que comparar, solo el hecho
  de que alguien pidió la simulación y con qué plazo.
"""

from io import StringIO

from django.contrib import messages
from django.core.management import call_command
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.permisos import requiere_permiso
from core.utils import get_client_ip

from ..auditoria import auditar_cambios
from ..forms import RetencionForm
from ..models import ConfiguracionSistema
from ..services import registrar_auditoria


@requiere_permiso("administracion", "escritura")
def datos(request):
    """Edita los dos plazos de retención del historial.

    Exige escritura, como las demás pantallas de configuración: lo que se
    guarda aquí decide qué se borra para siempre la próxima madrugada del
    domingo.
    """
    config = ConfiguracionSistema.get_config()

    if request.method == "POST":
        form = RetencionForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            auditar_cambios(request.user, form, ip=get_client_ip(request))
            messages.success(request, "Política de retención actualizada.")
            return redirect("administracion:datos")
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = RetencionForm(instance=config)

    return render(request, "administracion/datos_form.html", {
        "form": form,
        "config": config,
    })


@requiere_permiso("administracion", "escritura")
@require_POST
def simular_limpieza(request):
    """Corre la limpieza en seco y muestra lo que borraría, sin borrar nada.

    El comando se invoca **sin** ``--dias`` ni ``--media-dias`` a propósito: así
    la simulación mide exactamente lo mismo que hará el cron, que tampoco los
    pasa. Si se le pasaran aquí, la pantalla podría decir una cosa y el
    programado hacer otra.
    """
    config = ConfiguracionSistema.get_config()
    salida = StringIO()
    error = ""
    try:
        call_command(
            "limpiar_historial",
            dry_run=True,
            sin_media=True,
            stdout=salida,
            stderr=salida,
        )
    # Un fallo del comando no puede dar un 500 en la pantalla de configuración:
    # se cuenta en el aviso y queda en la auditoría.
    except Exception as exc:
        error = str(exc)
        messages.error(request, f"No se pudo simular la limpieza: {error}")

    registrar_auditoria(
        request.user,
        "administracion",
        "configurar",
        objeto=config,
        detalle=(
            f"Simulación de limpieza con {config.retencion_dias} días de "
            f"historial y {config.retencion_media_dias} de archivos"
            + (f" (falló: {error})" if error else "")
        ),
        ip=get_client_ip(request),
    )

    return render(request, "administracion/datos_form.html", {
        "form": RetencionForm(instance=config),
        "config": config,
        "simulacion": salida.getvalue(),
    })
