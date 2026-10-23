"""Vistas del formato anterior de mantenimiento: estado de partes y checklist por orden."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permisos import requiere_permiso
from inventario.models import Activo

from ..forms import OrdenMantenimientoForm
from ..models import ChecklistItem, OrdenMantenimiento
from .ordenes import _parte_fields


@requiere_permiso("mantenimiento", "lectura")
def estado_partes_partial(request):
    activo_pk = request.GET.get("activo")
    activo = get_object_or_404(Activo, pk=activo_pk) if activo_pk else None
    orden_pk = request.GET.get("orden")
    if orden_pk:
        orden = get_object_or_404(OrdenMantenimiento, pk=orden_pk)
        form = OrdenMantenimientoForm(instance=orden, initial={"activo": activo} if activo else {})
    else:
        form = OrdenMantenimientoForm(initial={"activo": activo} if activo else {})
    return render(request, "mantenimiento/partials/estado_partes.html", {
        "form": form,
        "activo": activo,
        "parte_fields": _parte_fields(form),
    })


@requiere_permiso("mantenimiento", "escritura")
def toggle_checklist(request, pk):
    item = get_object_or_404(ChecklistItem, pk=pk, orden__isnull=False)
    if request.method == "POST":
        item.completado = not item.completado
        item.save(update_fields=["completado"])
    return render(request, "mantenimiento/partials/checklist_orden.html", {
        "orden": item.orden,
    })


@requiere_permiso("mantenimiento", "escritura")
def crear_item_checklist(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    if request.method == "POST":
        descripcion = request.POST.get("descripcion", "").strip()
        if descripcion:
            pos = orden.checklist_items.count()
            ChecklistItem.objects.create(
                orden=orden, descripcion=descripcion, posicion=pos
            )
            messages.success(request, "Ítem agregado al checklist.")
        else:
            messages.error(request, "Escribe una descripción para el ítem.")
    return redirect("mantenimiento:detalle_orden", pk=orden.pk)
