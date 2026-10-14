import mimetypes
import posixpath
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.permisos import PERMISOS_POR_ROL
from inventario.models import Activo
from mantenimiento.models import OrdenMantenimiento
from usuarios.models import Usuario


@login_required
def dashboard(request):
    hoy = timezone.now().date()
    ordenes_abiertas = OrdenMantenimiento.objects.filter(
        estado__in=["abierta", "en_proceso"]
    )
    ordenes_atrasadas = ordenes_abiertas.filter(
        plan__isnull=False,
        plan__proxima_ejecucion__lt=hoy,
    )
    context = {
        "total_usuarios": Usuario.objects.filter(estado="activo").count(),
        "total_activos": Activo.objects.count(),
        "activos_asignados": Activo.objects.filter(estado="asignado").count(),
        "activos_disponibles": Activo.objects.filter(estado="disponible").count(),
        "activos_baja": Activo.objects.filter(estado="dado_de_baja").count(),
        "ordenes_abiertas": ordenes_abiertas.count(),
        "ordenes_atrasadas": ordenes_atrasadas.count(),
    }
    return render(request, "core/dashboard.html", context)


# Prefijo de MEDIA_ROOT -> módulo cuyo permiso protege esos archivos.
MEDIA_PERMISOS = (
    ("usuarios/fotos/", "usuarios"),
    ("inventario/fotos/", "inventario"),
    ("inventario/actas/", "inventario"),
    ("mantenimiento/fotos/", "mantenimiento"),
    ("documentos/", "documentos"),
)

# Tipos que se pueden mostrar en el navegador; el resto se fuerza a descarga.
MEDIA_INLINE = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}


@login_required
def media_protegido(request, ruta):
    limpio = posixpath.normpath(ruta)
    if (
        "\x00" in ruta
        or "\\" in ruta
        or limpio != ruta  # rechaza '..', '//', './', rutas no normalizadas
        or limpio.startswith(("/", ".."))
    ):
        raise Http404

    modulo = next((m for pref, m in MEDIA_PERMISOS if limpio.startswith(pref)), None)
    if modulo is None:
        raise Http404  # prefijo no registrado: denegar por defecto

    if not request.user.is_superuser:
        nivel = PERMISOS_POR_ROL.get(request.user.rol, {}).get(modulo, "ninguno")
        if nivel == "ninguno":
            raise Http404

    raiz = Path(settings.MEDIA_ROOT).resolve()
    destino = (raiz / limpio).resolve()
    if raiz not in destino.parents or not destino.is_file():
        raise Http404

    tipo = mimetypes.guess_type(destino.name)[0] or "application/octet-stream"
    disposicion = "inline" if tipo in MEDIA_INLINE else "attachment"

    if getattr(settings, "MEDIA_ACCEL_REDIRECT", False):
        resp = HttpResponse()
        resp["X-Accel-Redirect"] = f"/_protegido/{limpio}"
    else:
        resp = FileResponse(destino.open("rb"))

    resp["Content-Type"] = tipo
    resp["Content-Disposition"] = f'{disposicion}; filename="{destino.name}"'
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "private, max-age=3600"
    return resp
