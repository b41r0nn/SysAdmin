"""Órdenes de mantenimiento: lista, detalle, alta, edición, cierre y baja, con sus repuestos y fotos."""

from django import forms
from django.contrib import messages
from django.db.models import DecimalField, F, Q, Sum
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.permisos import requiere_permiso
from inventario.models import Activo

from ..constants import PARTES_POR_TIPO
from ..forms import FotoMantenimientoForm, OrdenMantenimientoForm, RepuestoForm
from ..models import (
    ESTADOS_ORDEN,
    PRIORIDADES,
    TIPOS_MANTENIMIENTO,
    FotoMantenimiento,
    OrdenMantenimiento,
    PlanMantenimiento,
    Repuesto,
)
from ..services import snapshot_software_ocs
from .planes import _actualizar_plan_por_orden, _copiar_checklist_plantilla


FotoFormSet = modelformset_factory(
    FotoMantenimiento, form=FotoMantenimientoForm, extra=3, can_delete=True
)


# El formset de fotos se instancia SIEMPRE con prefix="fotos": la plantilla y
# las validaciones de la vista dependen de ese prefijo (fotos-TOTAL_FORMS...).
def _foto_formset(*args, **kwargs):
    return FotoFormSet(*args, prefix="fotos", **kwargs)


def _parte_fields(form):
    return [field for field in form if field.name.startswith("parte_")]


@requiere_permiso("mantenimiento", "lectura")
def lista_ordenes(request):
    qs = OrdenMantenimiento.objects.select_related("activo", "plan")

    tipo = request.GET.get("tipo", "").strip()
    estado = request.GET.get("estado", "").strip()
    prioridad = request.GET.get("prioridad", "").strip()
    q = request.GET.get("q", "").strip()

    if tipo:
        qs = qs.filter(tipo=tipo)
    if estado:
        qs = qs.filter(estado=estado)
    if prioridad:
        qs = qs.filter(prioridad=prioridad)
    if q:
        qs = qs.filter(
            Q(activo__serial__icontains=q)
            | Q(activo__marca__icontains=q)
            | Q(activo__modelo__icontains=q)
            | Q(tecnico_asignado__icontains=q)
        )

    stats = {
        "total": qs.count(),
        "abiertas": qs.filter(estado="abierta").count(),
        "en_proceso": qs.filter(estado="en_proceso").count(),
        "cerradas": qs.filter(estado="cerrada").count(),
    }

    context = {
        "ordenes": qs,
        "filtro_tipo": tipo,
        "filtro_estado": estado,
        "filtro_prioridad": prioridad,
        "filtro_q": q,
        "stats": stats,
        "tipos": TIPOS_MANTENIMIENTO,
        "estados": ESTADOS_ORDEN,
        "prioridades": PRIORIDADES,
    }

    if request.headers.get("HX-Request"):
        return render(request, "mantenimiento/partials/tabla_ordenes.html", context)

    return render(request, "mantenimiento/lista_ordenes.html", context)


@requiere_permiso("mantenimiento", "lectura")
def detalle_orden(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    repuestos = orden.repuestos.all().order_by("nombre")
    repuestos_total = repuestos.aggregate(
        total=Sum(F("costo_unitario") * F("cantidad"), output_field=DecimalField())
    )
    fotos = orden.fotos.all()

    partes_labels = dict(PARTES_POR_TIPO.get(orden.activo.tipo_dispositivo, []))
    estado_partes_items = [
        (partes_labels.get(slug, slug), estado)
        for slug, estado in (orden.estado_partes or {}).items()
    ]

    return render(request, "mantenimiento/detalle_orden.html", {
        "orden": orden,
        "repuestos": repuestos,
        "repuestos_total": repuestos_total.get("total") or 0,
        "fotos": fotos,
        "estado_partes_items": estado_partes_items,
    })


@requiere_permiso("mantenimiento", "escritura")
def crear_orden(request):
    if request.method == "POST":
        hay_fotos = "fotos-TOTAL_FORMS" in request.POST
        fset = (
            _foto_formset(request.POST, request.FILES, queryset=FotoMantenimiento.objects.none())
            if hay_fotos
            else None
        )
        if fset is not None:
            fset_valid = fset.is_valid()
        else:
            fset_valid = True
        form = OrdenMantenimientoForm(request.POST)
        if form.is_valid() and fset_valid:
            # Snapshot automático de software desde OCS si el textarea quedó vacío
            if not form.cleaned_data.get("software_snapshot_text"):
                activo = form.cleaned_data.get("activo")
                if activo:
                    software = snapshot_software_ocs(activo)
                    if software:
                        form.instance.software_snapshot = [
                            s.get("name") for s in software if s.get("name")
                        ]
            orden = form.save()
            _copiar_checklist_plantilla(orden)
            if fset is not None:
                for foto in fset.save(commit=False):
                    foto.orden = orden
                    foto.save()
            messages.success(request, "Mantenimiento documentado correctamente.")
            return redirect("mantenimiento:detalle_orden", pk=orden.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        initial = {}
        activo_pk = request.GET.get("activo")
        plan_pk = request.GET.get("plan")
        if plan_pk:
            plan = get_object_or_404(PlanMantenimiento, pk=plan_pk)
            initial["plan"] = plan
        if activo_pk:
            activo = get_object_or_404(Activo, pk=activo_pk)
            software = snapshot_software_ocs(activo)
            initial.update({
                "activo": activo,
                "software_snapshot_text": "\n".join(
                    s["name"] for s in software if s.get("name")
                ),
            })
        form = OrdenMantenimientoForm(initial=initial)
        fset = _foto_formset(queryset=FotoMantenimiento.objects.none())

    return render(request, "mantenimiento/form_orden.html", {
        "form": form,
        "fset": fset,
        "titulo": "Documentar mantenimiento",
        "parte_fields": _parte_fields(form),
    })


@requiere_permiso("mantenimiento", "escritura")
def editar_orden(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    if request.method == "POST":
        hay_fotos = "fotos-TOTAL_FORMS" in request.POST
        fset = (
            _foto_formset(request.POST, request.FILES, queryset=orden.fotos.all())
            if hay_fotos
            else None
        )
        if fset is not None:
            fset_valid = fset.is_valid()
        else:
            fset_valid = True
        form = OrdenMantenimientoForm(request.POST, instance=orden)
        if form.is_valid() and fset_valid:
            orden = form.save()
            if fset is not None:
                for foto in fset.save(commit=False):
                    foto.orden = orden
                    foto.save()
                for foto in fset.deleted_objects:
                    foto.delete()
            messages.success(request, "Mantenimiento actualizado.")
            return redirect("mantenimiento:detalle_orden", pk=orden.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = OrdenMantenimientoForm(instance=orden)
        fset = _foto_formset(queryset=orden.fotos.all())

    return render(request, "mantenimiento/form_orden.html", {
        "form": form,
        "fset": fset,
        "titulo": "Editar mantenimiento",
        "orden": orden,
        "parte_fields": _parte_fields(form),
    })


@requiere_permiso("mantenimiento", "escritura")
def cerrar_orden(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    if request.method == "POST":
        if orden.estado == "cerrada":
            messages.warning(request, "La orden ya se encuentra cerrada.")
        else:
            orden.estado = "cerrada"
            orden.fecha_cierre = orden.fecha_cierre or timezone.now().date()
            orden.save(update_fields=["estado", "fecha_cierre", "fecha_actualizacion"])
            _actualizar_plan_por_orden(orden)
            messages.success(request, "Orden de mantenimiento cerrada.")
    return redirect("mantenimiento:detalle_orden", pk=orden.pk)


@requiere_permiso("mantenimiento", "escritura")
def eliminar_orden(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    if request.method == "POST":
        orden.delete()
        messages.success(request, "Orden de mantenimiento eliminada.")
        return redirect("mantenimiento:lista_ordenes")
    return redirect("mantenimiento:detalle_orden", pk=orden.pk)


@requiere_permiso("mantenimiento", "escritura")
def crear_repuesto(request, orden_pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=orden_pk)
    if request.method == "POST":
        form = RepuestoForm(request.POST)
        if form.is_valid():
            repuesto = form.save(commit=False)
            repuesto.orden = orden
            repuesto.save()
            messages.success(request, "Repuesto agregado correctamente.")
            return redirect("mantenimiento:detalle_orden", pk=orden.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = RepuestoForm(initial={"orden": orden})
    form.fields["orden"].widget = forms.HiddenInput()

    return render(request, "mantenimiento/form_repuesto.html", {
        "form": form,
        "orden": orden,
        "titulo": "Nuevo repuesto",
    })


@requiere_permiso("mantenimiento", "escritura")
def editar_repuesto(request, pk):
    repuesto = get_object_or_404(Repuesto, pk=pk)
    if request.method == "POST":
        form = RepuestoForm(request.POST, instance=repuesto)
        if form.is_valid():
            repuesto = form.save()
            messages.success(request, "Repuesto actualizado correctamente.")
            return redirect("mantenimiento:detalle_orden", pk=repuesto.orden_id)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = RepuestoForm(instance=repuesto)
    form.fields["orden"].widget = forms.HiddenInput()

    return render(request, "mantenimiento/form_repuesto.html", {
        "form": form,
        "orden": repuesto.orden,
        "titulo": "Editar repuesto",
        "repuesto": repuesto,
    })


@requiere_permiso("mantenimiento", "escritura")
def eliminar_repuesto(request, pk):
    repuesto = get_object_or_404(Repuesto, pk=pk)
    orden_id = repuesto.orden_id
    if request.method == "POST":
        repuesto.delete()
        messages.success(request, "Repuesto eliminado.")
        return redirect("mantenimiento:detalle_orden", pk=orden_id)
    return redirect("mantenimiento:detalle_orden", pk=orden_id)


@requiere_permiso("mantenimiento", "escritura")
def crear_foto(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    if request.method == "POST":
        form = FotoMantenimientoForm(request.POST, request.FILES)
        if form.is_valid():
            foto = form.save(commit=False)
            foto.orden = orden
            foto.save()
            messages.success(request, "Foto agregada al mantenimiento.")
        else:
            messages.error(request, "No se pudo subir la foto (formato o tamaño inválido).")
        return redirect("mantenimiento:detalle_orden", pk=orden.pk)
    return redirect("mantenimiento:detalle_orden", pk=orden.pk)


@requiere_permiso("mantenimiento", "escritura")
def eliminar_foto(request, pk):
    foto = get_object_or_404(FotoMantenimiento, pk=pk)
    orden_pk = foto.orden_id
    if request.method == "POST":
        foto.delete()
        messages.success(request, "Foto eliminada.")
    return redirect("mantenimiento:detalle_orden", pk=orden_pk)
