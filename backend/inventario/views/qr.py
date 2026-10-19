"""Etiquetas y vistas QR."""
import base64
import io
import os

import qrcode

import logging

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse


from administracion.models import ConfiguracionSistema

from ..models import (
    Activo,
)

from accounts.permisos import requiere_permiso

logger = logging.getLogger(__name__)



# ── Etiquetas QR ───────────────────────────────────────────────────────────────

LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "img", "logo_redihos_mark.png")


def _qr_png_bytes(url):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=7,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _qr_data_uri(url):
    return "data:image/png;base64," + base64.b64encode(_qr_png_bytes(url)).decode("ascii")


def _qr_url_publica(request, activo):
    """Construye la URL pública del QR, respetando QR_BASE_URL si está definida."""
    path = reverse("inventario:qr_publico_token", args=[activo.qr_token])
    base = settings.QR_BASE_URL.strip() if settings.QR_BASE_URL else ""
    if base:
        return f"{base.rstrip('/')}{path}"
    return request.build_absolute_uri(path)


def _etiqueta_context(request, activo):
    config = ConfiguracionSistema.get_config()
    return {
        "serial": activo.serial,
        "tipo": activo.get_tipo_dispositivo_display(),
        "marca": activo.marca,
        "modelo": activo.modelo,
        "numero_interno": activo.numero_interno,
        "qr": _qr_data_uri(_qr_url_publica(request, activo)),
        "logo_path": LOGO_PATH,
        "config": config,
    }


def _render_etiquetas_pdf(request, activos, filename):
    import weasyprint

    labels = [_etiqueta_context(request, a) for a in activos]
    html_string = render_to_string("inventario/etiqueta_pdf.html", {"labels": labels})
    pdf_bytes = weasyprint.HTML(
        string=html_string, base_url=request.build_absolute_uri("/")
    ).write_pdf()

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@requiere_permiso("inventario", "lectura")
def qr_etiqueta_pdf(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    return _render_etiquetas_pdf(request, [activo], f"etiqueta_{activo.serial}.pdf")


@requiere_permiso("inventario", "lectura")
def qr_etiquetas_masivas(request):
    if request.method == "POST":
        ids = [pk for pk in request.POST.getlist("activos") if pk]
        activos = Activo.objects.filter(pk__in=ids).order_by("serial")
        if not activos:
            messages.error(request, "Selecciona al menos un activo para generar etiquetas.")
            return redirect("inventario:etiquetas")
        return _render_etiquetas_pdf(request, activos, "etiquetas_qr.pdf")

    activos = Activo.objects.all().order_by("serial")
    return render(request, "inventario/etiquetas_seleccion.html", {"activos": activos})


def _static_url_publica(base_url, path):
    """Construye URL absoluta de un estático respetando QR_BASE_URL si existe."""
    base = (base_url or "").strip().rstrip("/")
    if base:
        return f"{base}{static(path)}"
    return static(path)


def qr_publico_token(request, token):
    """Vista pública al escanear un QR: diseño tipo etiqueta con logo.

    Se identifica por un UUID no adivinable para que no se pueda recorrer el
    inventario cambiando el número de la URL.
    """
    activo = get_object_or_404(Activo, qr_token=token)
    return _render_qr_publico(request, activo)


@requiere_permiso("inventario", "lectura")
def qr_publico(request, pk):
    """URL por id de las etiquetas impresas antes del token; requiere login."""
    return _render_qr_publico(request, get_object_or_404(Activo, pk=pk))


def _render_qr_publico(request, activo):
    config = ConfiguracionSistema.get_config()
    base = settings.QR_BASE_URL or request.build_absolute_uri("/")
    qr_url = _qr_url_publica(request, activo)
    return render(request, "inventario/qr_publico.html", {
        "activo": activo,
        "config": config,
        "logo_url": _static_url_publica(base, "img/logo_redihos_full.png"),
        "qr_data_uri": _qr_data_uri(qr_url),
    })


@requiere_permiso("inventario", "lectura")
def qr_imagen(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    png = _qr_png_bytes(_qr_url_publica(request, activo))
    response = HttpResponse(png, content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400"
    return response
