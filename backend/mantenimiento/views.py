from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import OrdenMantenimientoForm, PlanMantenimientoForm, RepuestoForm
from .models import (
    OrdenMantenimiento,
    PlanMantenimiento,
    Repuesto,
    TIPOS_MANTENIMIENTO,
    ESTADOS_PLAN,
    ESTADOS_ORDEN,
    PRIORIDADES,
)


# ── Planes ───────────────────────────────────────────────────────────────────

@login_required
def lista_planes(request):
    qs = PlanMantenimiento.objects.select_related("activo")

    tipo = request.GET.get("tipo", "").strip()
    estado = request.GET.get("estado", "").strip()
    q = request.GET.get("q", "").strip()

    if tipo:
        qs = qs.filter(tipo=tipo)
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(
            Q(activo__serial__icontains=q)
            | Q(activo__marca__icontains=q)
            | Q(activo__modelo__icontains=q)
        )

    stats = {
        "total": qs.count(),
        "activos": qs.filter(estado="activo").count(),
        "pausados": qs.filter(estado="pausado").count(),
    }
    hoy = timezone.now().date()
    limite_alerta = hoy + timedelta(days=7)

    context = {
        "planes": qs,
        "filtro_tipo": tipo,
        "filtro_estado": estado,
        "filtro_q": q,
        "stats": stats,
        "tipos": TIPOS_MANTENIMIENTO,
        "estados": ESTADOS_PLAN,
        "hoy": hoy,
        "limite_alerta": limite_alerta,
    }

    if request.headers.get("HX-Request"):
        return render(request, "mantenimiento/partials/tabla_planes.html", context)

    return render(request, "mantenimiento/lista_planes.html", context)


@login_required
def detalle_plan(request, pk):
    plan = get_object_or_404(PlanMantenimiento, pk=pk)
    ordenes = plan.ordenes.select_related("activo").all().order_by("-fecha_apertura")

    return render(request, "mantenimiento/detalle_plan.html", {
        "plan": plan,
        "ordenes": ordenes,
        "hoy": timezone.now().date(),
        "limite_alerta": timezone.now().date() + timedelta(days=7),
    })


@login_required
def crear_plan(request):
    if request.method == "POST":
        form = PlanMantenimientoForm(request.POST)
        if form.is_valid():
            plan = form.save()
            _set_proxima_ejecucion(plan)
            messages.success(request, "Plan de mantenimiento creado correctamente.")
            return redirect("mantenimiento:detalle_plan", pk=plan.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = PlanMantenimientoForm()

    return render(request, "mantenimiento/form_plan.html", {
        "form": form,
        "titulo": "Nuevo plan",
    })


@login_required
def editar_plan(request, pk):
    plan = get_object_or_404(PlanMantenimiento, pk=pk)
    if request.method == "POST":
        form = PlanMantenimientoForm(request.POST, instance=plan)
        if form.is_valid():
            plan = form.save()
            _set_proxima_ejecucion(plan)
            messages.success(request, "Plan de mantenimiento actualizado.")
            return redirect("mantenimiento:detalle_plan", pk=plan.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = PlanMantenimientoForm(instance=plan)

    return render(request, "mantenimiento/form_plan.html", {
        "form": form,
        "titulo": "Editar plan",
        "plan": plan,
    })


@login_required
def toggle_plan(request, pk):
    plan = get_object_or_404(PlanMantenimiento, pk=pk)
    if request.method == "POST":
        if plan.estado == "activo":
            plan.estado = "pausado"
            messages.warning(request, "Plan de mantenimiento pausado.")
        else:
            plan.estado = "activo"
            messages.success(request, "Plan de mantenimiento reactivado.")
        plan.save(update_fields=["estado", "fecha_actualizacion"])
    return redirect("mantenimiento:detalle_plan", pk=plan.pk)


# ── Ordenes ─────────────────────────────────────────────────────────────────-

@login_required
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


@login_required
def detalle_orden(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    repuestos = orden.repuestos.all().order_by("nombre")
    repuestos_total = repuestos.aggregate(
        total=Sum(F("costo_unitario") * F("cantidad"), output_field=DecimalField())
    )

    return render(request, "mantenimiento/detalle_orden.html", {
        "orden": orden,
        "repuestos": repuestos,
        "repuestos_total": repuestos_total.get("total") or 0,
    })


@login_required
def crear_orden(request):
    if request.method == "POST":
        form = OrdenMantenimientoForm(request.POST)
        if form.is_valid():
            orden = form.save()
            messages.success(request, "Orden de mantenimiento creada correctamente.")
            return redirect("mantenimiento:detalle_orden", pk=orden.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = OrdenMantenimientoForm(initial={"fecha_apertura": timezone.now().date()})

    return render(request, "mantenimiento/form_orden.html", {
        "form": form,
        "titulo": "Nueva orden",
    })


@login_required
def editar_orden(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    if request.method == "POST":
        form = OrdenMantenimientoForm(request.POST, instance=orden)
        if form.is_valid():
            orden = form.save()
            messages.success(request, "Orden de mantenimiento actualizada.")
            return redirect("mantenimiento:detalle_orden", pk=orden.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = OrdenMantenimientoForm(instance=orden)

    return render(request, "mantenimiento/form_orden.html", {
        "form": form,
        "titulo": "Editar orden",
        "orden": orden,
    })


@login_required
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


@login_required
def eliminar_plan(request, pk):
    plan = get_object_or_404(PlanMantenimiento, pk=pk)
    if request.method == "POST":
        if plan.ordenes.exists():
            messages.error(request, "No puedes eliminar un plan con ordenes asociadas.")
            return redirect("mantenimiento:detalle_plan", pk=plan.pk)
        plan.delete()
        messages.success(request, "Plan de mantenimiento eliminado.")
        return redirect("mantenimiento:lista_planes")
    return redirect("mantenimiento:detalle_plan", pk=plan.pk)


@login_required
def eliminar_orden(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    if request.method == "POST":
        orden.delete()
        messages.success(request, "Orden de mantenimiento eliminada.")
        return redirect("mantenimiento:lista_ordenes")
    return redirect("mantenimiento:detalle_orden", pk=orden.pk)


@login_required
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


@login_required
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


@login_required
def eliminar_repuesto(request, pk):
    repuesto = get_object_or_404(Repuesto, pk=pk)
    orden_id = repuesto.orden_id
    if request.method == "POST":
        repuesto.delete()
        messages.success(request, "Repuesto eliminado.")
        return redirect("mantenimiento:detalle_orden", pk=orden_id)
    return redirect("mantenimiento:detalle_orden", pk=orden_id)


def _set_proxima_ejecucion(plan):
    if plan.tipo != "preventivo":
        return
    if not plan.frecuencia_dias or not plan.fecha_inicio:
        return
    if plan.proxima_ejecucion:
        return
    plan.proxima_ejecucion = plan.fecha_inicio + timedelta(days=plan.frecuencia_dias)
    plan.save(update_fields=["proxima_ejecucion", "fecha_actualizacion"])


def _actualizar_plan_por_orden(orden):
    if orden.tipo != "preventivo":
        return
    if not orden.plan:
        return
    if not orden.plan.frecuencia_dias:
        return
    base = orden.fecha_cierre or timezone.now().date()
    orden.plan.proxima_ejecucion = base + timedelta(days=orden.plan.frecuencia_dias)
    orden.plan.save(update_fields=["proxima_ejecucion", "fecha_actualizacion"])
