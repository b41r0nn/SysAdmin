"""Acta de mantenimiento en PDF (una hoja carta), generada desde los datos congelados al cerrar."""

import re

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect

from accounts.permisos import requiere_permiso

from .. import acta as servicio
from ..models import FORMATO_ACTUAL, OrdenMantenimiento


@requiere_permiso("mantenimiento", "lectura")
def acta_pdf(request, pk):
    orden = get_object_or_404(OrdenMantenimiento.objects.select_related("activo"), pk=pk)
    if orden.formato != FORMATO_ACTUAL:
        messages.info(request, "Esta orden es del formato anterior: usa su PDF.")
        return redirect("mantenimiento:detalle_orden", pk=orden.pk)
    if orden.estado != "cerrada":
        messages.warning(request, "El acta se genera cuando el mantenimiento está cerrado.")
        return redirect("mantenimiento:detalle_orden", pk=orden.pk)
    if not orden.datos_acta:
        messages.warning(request, "Faltan los datos del acta: reabre el mantenimiento y ciérralo de nuevo.")
        return redirect("mantenimiento:detalle_orden", pk=orden.pk)

    pdf, _escala = servicio.renderizar_acta(orden, request)
    # El serial va en el nombre del archivo: fuera lo que rompería la cabecera.
    serial = re.sub(r"[^\w.-]", "_", orden.activo.serial, flags=re.ASCII)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="acta_mantenimiento_{orden.pk:04d}_{serial}.pdf"'
    return response
