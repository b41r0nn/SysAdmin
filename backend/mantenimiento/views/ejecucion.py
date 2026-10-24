"""Ejecución de un preventivo: alta del mantenimiento y marcado del checklist."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.permisos import requiere_permiso
from inventario.models import Activo

from .. import ejecucion as servicio
from ..forms import NuevoMantenimientoForm
from ..models import ChecklistItem


def contexto_checklist(orden, error=None, error_item=None, obs_tecleada=""):
    """Datos que necesita la tarjeta del checklist de ejecución."""
    items = list(orden.checklist_items.all())
    return {
        "orden": orden,
        "items": items,
        "total": len(items),
        "marcados": sum(1 for i in items if i.resultado),
        "editable": orden.estado in servicio.ESTADOS_ABIERTOS,
        "error": error,
        "error_item": error_item,
        "obs_tecleada": obs_tecleada,
    }


def _mensaje(error):
    return " ".join(error.messages)


@requiere_permiso("mantenimiento", "escritura")
def nuevo(request):
    if request.method == "POST":
        form = NuevoMantenimientoForm(request.POST)
        if form.is_valid():
            activo = form.cleaned_data["activo"]
            if form.cleaned_data["tipo"] == "correctivo":
                return redirect(f"{reverse('mantenimiento:crear_orden')}?activo={activo.pk}")
            try:
                orden = servicio.iniciar_preventivo(activo, request.user)
            except ValidationError as e:
                form.add_error(None, _mensaje(e))
            else:
                return redirect("mantenimiento:detalle_orden", pk=orden.pk)
    else:
        inicial = {}
        activo_pk = request.GET.get("activo", "")
        if activo_pk.isdigit():
            inicial["activo"] = activo_pk
        form = NuevoMantenimientoForm(initial=inicial)
    return render(request, "mantenimiento/nuevo.html", {"form": form})


@requiere_permiso("mantenimiento", "escritura")
@require_POST
def iniciar_preventivo(request, activo_pk):
    activo = get_object_or_404(Activo, pk=activo_pk)
    try:
        orden = servicio.iniciar_preventivo(activo, request.user)
    except ValidationError as e:
        messages.error(request, _mensaje(e))
        volver = request.POST.get("volver", "")
        if volver and url_has_allowed_host_and_scheme(
            volver, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(volver)
        return redirect("mantenimiento:nuevo")
    return redirect("mantenimiento:detalle_orden", pk=orden.pk)


@requiere_permiso("mantenimiento", "escritura")
@require_POST
def marcar_punto(request, pk):
    item = get_object_or_404(ChecklistItem, pk=pk, orden__isnull=False)
    error = None
    try:
        servicio.marcar_punto(
            item, request.POST.get("resultado", ""), request.POST.get("observacion", "")
        )
    except ValidationError as e:
        error = _mensaje(e)
    if request.htmx:
        orden = item.orden
        return render(
            request,
            "mantenimiento/partials/checklist_ejecucion.html",
            contexto_checklist(
                orden, error, item.pk if error else None, request.POST.get("observacion", "")
            ),
        )
    if error:
        messages.error(request, error)
    return redirect("mantenimiento:detalle_orden", pk=item.orden_id)
