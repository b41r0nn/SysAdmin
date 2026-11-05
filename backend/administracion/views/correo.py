"""Pantalla de Correo: servidor SMTP, remitente, prueba de envío y cola.

Es la única pantalla que escribe la contraseña del correo, y la credencial
manda sobre el resto del diseño:

- el formulario guarda la clave cifrada y, en blanco, conserva la anterior;
- el cambio se audita con ``secretos=("smtp_password",)``, así que el registro
  dice «(cambiada)» y nunca el valor;
- el correo de prueba se manda **directo sobre la conexión**, sin pasar por
  ``NotificacionEmail``: esa tabla es un histórico que el cron reenvía, y un
  secreto de configuración no tiene por qué acabar ahí;
- el texto del fallo que se muestra en pantalla se limpia antes con
  ``administracion.errores_correo.texto_de_error_smtp()``, el **mismo** que usa
  la cola: un ``except`` que vuelque la respuesta del servidor tal cual puede
  devolver lo que le mandamos, y tener un tachado por camino es tener uno sin
  tachado.
"""

from django.contrib import messages
from django.core.mail import EmailMessage
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.permisos import requiere_permiso
from core.utils import get_client_ip
from notificaciones.models import NotificacionEmail
# Import por nombre (y no `services._get_smtp_connection`) para que las pruebas
# puedan parchear `administracion.views.correo._get_smtp_connection`.
from notificaciones.services import MAX_INTENTOS_EMAIL, _get_smtp_connection

from ..auditoria import auditar_cambios
from ..errores_correo import texto_de_error_smtp
from ..forms import CorreoForm
from ..models import ConfiguracionSistema
from ..services import registrar_auditoria

SIN_SMTP = (
    "No hay servidor SMTP configurado: guarda el servidor y el usuario antes "
    "de probar el envío."
)
ASUNTO_PRUEBA = "Correo de prueba de SysAdmin"


def _conteos_de_la_cola():
    """Pendientes, fallidos y enviados de ``NotificacionEmail``.

    «Fallido» es el que agotó los intentos: la cola ya no lo toma, así que solo
    sale de ahí con el botón de reintentar.
    """
    sin_enviar = NotificacionEmail.objects.filter(enviado=False)
    return {
        "pendientes": sin_enviar.filter(intentos__lt=MAX_INTENTOS_EMAIL).count(),
        "fallidos": sin_enviar.filter(intentos__gte=MAX_INTENTOS_EMAIL).count(),
        "enviados": NotificacionEmail.objects.filter(enviado=True).count(),
        "ultimos": NotificacionEmail.objects.filter(enviado=False).order_by(
            "-fecha_creacion"
        )[:10],
        "max_intentos": MAX_INTENTOS_EMAIL,
    }


@requiere_permiso("administracion", "escritura")
def correo(request):
    """Edita la configuración del correo y muestra el estado de la cola."""
    config = ConfiguracionSistema.get_config()

    if request.method == "POST":
        form = CorreoForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            # `secretos` no es opcional aquí: sin él el renglón de auditoría
            # queda «Contraseña SMTP: (vacío) → <la clave>», en claro y para
            # siempre, en una tabla que la pantalla de Auditoría muestra.
            auditar_cambios(
                request.user, form, ip=get_client_ip(request),
                secretos=("smtp_password",),
            )
            messages.success(request, "Configuración de correo actualizada.")
            return redirect("administracion:correo")
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = CorreoForm(instance=config)

    return render(request, "administracion/correo_form.html", {
        "form": form,
        "config": config,
        **_conteos_de_la_cola(),
    })


@requiere_permiso("administracion", "escritura")
@require_POST
def probar_correo(request):
    """Manda un correo de prueba y cuenta en pantalla qué dijo el servidor."""
    config = ConfiguracionSistema.get_config()
    destino = (request.POST.get("destino") or "").strip()
    if not destino:
        messages.error(request, "Escribe la dirección a la que enviar la prueba.")
        return redirect("administracion:correo")

    try:
        conexion = _get_smtp_connection()
    except Exception as exc:
        messages.error(request, f"No se pudo abrir la conexión: {texto_de_error_smtp(exc, config)}")
        return redirect("administracion:correo")

    if conexion is None:
        messages.warning(request, SIN_SMTP)
        return redirect("administracion:correo")

    enviado = False
    try:
        EmailMessage(
            subject=ASUNTO_PRUEBA,
            body=(
                f"Este es un correo de prueba enviado desde SysAdmin "
                f"({config.nombre_empresa}).\n\n"
                "Si lo recibiste, la configuración del servidor SMTP funciona."
            ),
            from_email=config.remitente_efectivo(),
            to=[destino],
            connection=conexion,
        ).send(fail_silently=False)
        enviado = True
    except Exception as exc:
        messages.error(
            request,
            f"No se pudo enviar el correo de prueba: {texto_de_error_smtp(exc, config)}",
        )
    finally:
        try:
            conexion.close()
        except Exception:
            pass

    if enviado:
        messages.success(request, f"Correo de prueba enviado a {destino}.")

    # Se audita el destino y el resultado, nunca la credencial ni el texto del
    # error del servidor.
    registrar_auditoria(
        request.user,
        "administracion",
        "configurar",
        objeto=config,
        detalle=f"Correo de prueba a {destino}: {'enviado' if enviado else 'falló'}",
        ip=get_client_ip(request),
    )
    return redirect("administracion:correo")


@requiere_permiso("administracion", "escritura")
@require_POST
def reintentar_correos(request):
    """Devuelve a la cola los correos sin enviar: ``intentos=0`` y sin error."""
    config = ConfiguracionSistema.get_config()
    devueltos = NotificacionEmail.objects.filter(enviado=False).update(
        intentos=0, error="",
    )
    if devueltos:
        messages.success(
            request,
            f"{devueltos} correo(s) de vuelta en la cola. El envío lo hace la "
            "tarea programada.",
        )
        registrar_auditoria(
            request.user,
            "administracion",
            "configurar",
            objeto=config,
            detalle=f"Cola de correo: {devueltos} correo(s) devueltos a la cola",
            ip=get_client_ip(request),
        )
    else:
        messages.info(request, "No hay correos sin enviar en la cola.")
    return redirect("administracion:correo")
