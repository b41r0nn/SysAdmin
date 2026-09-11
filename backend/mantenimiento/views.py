from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from accounts.permisos import PERMISOS_POR_ROL, requiere_permiso
from notificaciones.services import aviso_usuario, encolar_email

from .forms import (
    ChecklistItemForm,
    OrdenMantenimientoForm,
    PlanMantenimientoForm,
    ReporteFallaForm,
    RepuestoForm,
)
from .models import (
    ChecklistItem,
    OrdenMantenimiento,
    PlanMantenimiento,
    Repuesto,
    TIPOS_MANTENIMIENTO,
    ESTADOS_PLAN,
    ESTADOS_ORDEN,
    PRIORIDADES,
    CRITICIDADES,
)

from django.forms import modelformset_factory

ChecklistItemFormSet = modelformset_factory(
    ChecklistItem, form=ChecklistItemForm, extra=3, can_delete=True
)


# ── Planes ───────────────────────────────────────────────────────────────────

@requiere_permiso("mantenimiento", "lectura")
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


# ── Ordenes ─────────────────────────────────────────────────────────────────-

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

    return render(request, "mantenimiento/detalle_orden.html", {
        "orden": orden,
        "repuestos": repuestos,
        "repuestos_total": repuestos_total.get("total") or 0,
    })


@requiere_permiso("mantenimiento", "escritura")
def crear_orden(request):
    if request.method == "POST":
        form = OrdenMantenimientoForm(request.POST)
        if form.is_valid():
            orden = form.save()
            _copiar_checklist_plantilla(orden)
            messages.success(request, "Orden de mantenimiento creada correctamente.")
            return redirect("mantenimiento:detalle_orden", pk=orden.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        initial = {}
        plan_pk = request.GET.get("plan")
        if plan_pk:
            plan = get_object_or_404(PlanMantenimiento, pk=plan_pk)
            initial = {
                "plan": plan,
                "activo": plan.activo,
                "tipo": plan.tipo,
                "descripcion": f"Ejecutar plan {plan.get_tipo_display()} del activo {plan.activo.serial}.",
            }
        form = OrdenMantenimientoForm(initial=initial)

    return render(request, "mantenimiento/form_orden.html", {
        "form": form,
        "titulo": "Nueva orden",
    })


@requiere_permiso("mantenimiento", "escritura")
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


# ── Checklist ───────────────────────────────────────────────────────────────

@requiere_permiso("mantenimiento", "escritura")
def toggle_checklist(request, pk):
    item = get_object_or_404(ChecklistItem, pk=pk, orden__isnull=False)
    if request.method == "POST":
        item.completado = not item.completado
        item.save(update_fields=["completado"])
    return render(request, "mantenimiento/partials/checklist_orden.html", {
        "orden": item.orden,
    })


# ── Calendario ──────────────────────────────────────────────────────────────

@requiere_permiso("mantenimiento", "lectura")
def calendario(request):
    return render(request, "mantenimiento/calendario.html")


@requiere_permiso("mantenimiento", "lectura")
def calendario_eventos(request):
    colores_estado = {
        "abierta": "#0d6efd",
        "en_proceso": "#ffc107",
        "cerrada": "#198754",
        "cancelada": "#6c757d",
        "reportada": "#dc3545",
    }
    colores_criticidad = {
        "baja": "#198754",
        "media": "#ffc107",
        "alta": "#dc3545",
    }
    eventos = []

    for orden in OrdenMantenimiento.objects.select_related("activo").all():
        eventos.append({
            "title": f"Orden #{orden.id} · {orden.activo.serial}",
            "start": orden.fecha_apertura.isoformat(),
            "url": reverse("mantenimiento:detalle_orden", args=[orden.pk]),
            "color": colores_estado.get(orden.estado, "#0d6efd"),
        })

    for plan in PlanMantenimiento.objects.select_related("activo").filter(
        estado="activo", proxima_ejecucion__isnull=False
    ):
        eventos.append({
            "title": f"Plan {plan.get_tipo_display()} · {plan.activo.serial}",
            "start": plan.proxima_ejecucion.isoformat(),
            "url": reverse("mantenimiento:detalle_plan", args=[plan.pk]),
            "color": colores_criticidad.get(plan.criticidad, "#ffc107"),
        })

    return JsonResponse(eventos, safe=False)


# ── Portal de reporte ───────────────────────────────────────────────────────

@login_required
def reportar(request):
    if request.method == "POST":
        form = ReporteFallaForm(request.POST)
        if form.is_valid():
            orden = form.save(commit=False)
            orden.tipo = "correctivo"
            orden.estado = "reportada"
            orden.fecha_apertura = timezone.now().date()
            orden.reportado_por = request.user
            orden.save()
            messages.success(request, "Falla reportada. El equipo de TI se encargará.")
            _notificar_tecnico(orden)
            return redirect("core:dashboard")
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = ReporteFallaForm(initial={"prioridad": "alta"})

    return render(request, "mantenimiento/form_reporte.html", {"form": form})


def _notificar_tecnico(orden):
    titulo = f"Nueva orden #{orden.id} reportada · {orden.activo.serial}"
    mensaje = (
        f"{orden.reportado_por.get_full_name() or orden.reportado_por.username} "
        f"reportó un problema con {orden.activo.marca} {orden.activo.modelo}."
    )
    link = reverse("mantenimiento:detalle_orden", args=[orden.pk])
    tecnicos = get_user_model().objects.filter(
        is_active=True, rol__in={"superadmin", "admin", "tecnico"}
    )
    for user in tecnicos:
        aviso_usuario(user, titulo, mensaje, link=link, objetokey=f"orden:{orden.pk}")
        encolar_email(user.email, titulo, mensaje)


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
