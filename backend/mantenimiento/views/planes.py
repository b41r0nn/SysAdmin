"""Planes de mantenimiento: lista, detalle, alta, edición, pausa y baja, con su checklist."""

from datetime import timedelta

from django.contrib import messages
from django.db.models import Q
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.permisos import requiere_permiso

from ..forms import ChecklistItemForm, PlanMantenimientoForm
from ..models import ESTADOS_PLAN, TIPOS_MANTENIMIENTO, ChecklistItem, PlanMantenimiento


ChecklistItemFormSet = modelformset_factory(
    ChecklistItem, form=ChecklistItemForm, extra=3, can_delete=True
)


@requiere_permiso("mantenimiento", "lectura")
def lista_planes(request):
    qs = PlanMantenimiento.objects.all()

    tipo = request.GET.get("tipo", "").strip()
    estado = request.GET.get("estado", "").strip()
    q = request.GET.get("q", "").strip()

    if tipo:
        qs = qs.filter(tipo=tipo)
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(Q(tipo_dispositivo__icontains=q))

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


@requiere_permiso("mantenimiento", "lectura")
def detalle_plan(request, pk):
    plan = get_object_or_404(PlanMantenimiento, pk=pk)
    ordenes = plan.ordenes.select_related("activo").all().order_by("-fecha_apertura")

    return render(request, "mantenimiento/detalle_plan.html", {
        "plan": plan,
        "ordenes": ordenes,
        "hoy": timezone.now().date(),
        "limite_alerta": timezone.now().date() + timedelta(days=7),
    })


def _formset_checklist(request, plan=None):
    qs = plan.checklist_items.all() if plan else ChecklistItem.objects.none()
    if request.method == "POST" and "form-TOTAL_FORMS" in request.POST:
        return ChecklistItemFormSet(request.POST, queryset=qs)
    return ChecklistItemFormSet(queryset=qs)


def _checklist_enviado(request):
    return request.method == "POST" and "form-TOTAL_FORMS" in request.POST


@requiere_permiso("mantenimiento", "escritura")
def crear_plan(request):
    if request.method == "POST":
        form = PlanMantenimientoForm(request.POST)
        fset = _formset_checklist(request)
        fset_valido = fset.is_valid() if _checklist_enviado(request) else True
        if form.is_valid() and fset_valido:
            plan = form.save()
            _set_proxima_ejecucion(plan)
            if _checklist_enviado(request):
                _guardar_checklist_items(fset, plan)
            messages.success(request, "Plan de mantenimiento creado correctamente.")
            return redirect("mantenimiento:detalle_plan", pk=plan.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = PlanMantenimientoForm()
        fset = _formset_checklist(request)

    return render(request, "mantenimiento/form_plan.html", {
        "form": form,
        "fset": fset,
        "titulo": "Nuevo plan",
    })


@requiere_permiso("mantenimiento", "escritura")
def editar_plan(request, pk):
    plan = get_object_or_404(PlanMantenimiento, pk=pk)
    if request.method == "POST":
        form = PlanMantenimientoForm(request.POST, instance=plan)
        fset = _formset_checklist(request, plan)
        fset_valido = fset.is_valid() if _checklist_enviado(request) else True
        if form.is_valid() and fset_valido:
            plan = form.save()
            _set_proxima_ejecucion(plan)
            if _checklist_enviado(request):
                _guardar_checklist_items(fset, plan)
            messages.success(request, "Plan de mantenimiento actualizado.")
            return redirect("mantenimiento:detalle_plan", pk=plan.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = PlanMantenimientoForm(instance=plan)
        fset = _formset_checklist(request, plan)

    return render(request, "mantenimiento/form_plan.html", {
        "form": form,
        "fset": fset,
        "titulo": "Editar plan",
        "plan": plan,
    })


@requiere_permiso("mantenimiento", "escritura")
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


@requiere_permiso("mantenimiento", "escritura")
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


def _guardar_checklist_items(fset, plan):
    for item in fset.save(commit=False):
        item.plan_id = plan.pk
        item.save()
    for item in fset.deleted_objects:
        item.delete()
    for i, item in enumerate(plan.checklist_items.all().order_by("posicion", "id")):
        if item.posicion != i:
            item.posicion = i
            item.save(update_fields=["posicion"])


def _copiar_checklist_plantilla(orden):
    if not orden.plan_id:
        return
    for item in orden.plan.checklist_items.all().order_by("posicion", "id"):
        ChecklistItem.objects.create(
            orden=orden,
            descripcion=item.descripcion,
            posicion=item.posicion,
        )


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
