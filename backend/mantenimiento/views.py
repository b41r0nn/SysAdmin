import os
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from accounts.permisos import PERMISOS_POR_ROL, requiere_permiso
from administracion.models import ConfiguracionSistema
from inventario.models import Activo
from notificaciones.services import aviso_usuario, encolar_email

from .forms import (
    ChecklistItemForm,
    FotoMantenimientoForm,
    OrdenMantenimientoForm,
    PlanMantenimientoForm,
    ReporteFallaForm,
    RepuestoForm,
)
from .models import (
    ChecklistItem,
    FotoMantenimiento,
    OrdenMantenimiento,
    PlanMantenimiento,
    Repuesto,
    TIPOS_MANTENIMIENTO,
    ESTADOS_PLAN,
    ESTADOS_ORDEN,
    PRIORIDADES,
    CRITICIDADES,
)
from .constants import PARTES_POR_TIPO
from .services import snapshot_software_ocs

from django.forms import modelformset_factory

ChecklistItemFormSet = modelformset_factory(
    ChecklistItem, form=ChecklistItemForm, extra=3, can_delete=True
)

FotoFormSet = modelformset_factory(
    FotoMantenimiento, form=FotoMantenimientoForm, extra=3, can_delete=True
)

# El formset de fotos se instancia SIEMPRE con prefix="fotos": la plantilla y
# las validaciones de la vista dependen de ese prefijo (fotos-TOTAL_FORMS...).
def _foto_formset(*args, **kwargs):
    return FotoFormSet(*args, prefix="fotos", **kwargs)


def _parte_fields(form):
    return [field for field in form if field.name.startswith("parte_")]


# ── Planes ───────────────────────────────────────────────────────────────────

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

    for plan in PlanMantenimiento.objects.filter(
        estado="activo", proxima_ejecucion__isnull=False
    ):
        eventos.append({
            "title": f"Plan {plan.get_tipo_display()} · {plan.tipo_dispositivo}",
            "start": plan.proxima_ejecucion.isoformat(),
            "url": reverse("mantenimiento:detalle_plan", args=[plan.pk]),
            "color": colores_criticidad.get(plan.criticidad, "#ffc107"),
        })

    return JsonResponse(eventos, safe=False)


# ── Portal de reporte ───────────────────────────────────────────────────────

@login_required
def reportar(request):
    if request.method == "POST":
        form = ReporteFallaForm(request.POST, request.FILES)
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


# ── Hoja de vida por activo ──────────────────────────────────────────────────

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


@requiere_permiso("mantenimiento", "lectura")
def hoja_de_vida(request, activo_pk):
    from inventario.models import Activo

    activo = get_object_or_404(Activo, pk=activo_pk)
    ordenes = (
        OrdenMantenimiento.objects.filter(activo=activo)
        .select_related("plan")
        .order_by("-fecha_apertura", "-fecha_creacion")
    )
    ultima = ordenes.first()
    fotos = FotoMantenimiento.objects.filter(orden__activo=activo).order_by("-fecha_creacion")
    equipo_ocs = activo.equipo_ocs.first() if activo.equipo_ocs.exists() else None
    software_ultimo = []
    if ultima and ultima.software_snapshot:
        software_ultimo = ultima.software_snapshot
        if isinstance(software_ultimo, list) and software_ultimo and isinstance(software_ultimo[0], dict):
            software_ultimo = [
                s.get("name") if isinstance(s, dict) else str(s) for s in software_ultimo
            ]

    acciones_ultimas = []
    estado_partes_items = []
    if ultima:
        if ultima.accion_limpieza_general:
            acciones_ultimas.append("Limpieza general")
        if ultima.accion_mantenimiento_logico:
            acciones_ultimas.append("Mantenimiento lógico")
        if ultima.accion_cambio_pasta_termica:
            acciones_ultimas.append("Cambio de pasta térmica")
        if ultima.accion_cambio_parte:
            acciones_ultimas.append("Cambio de parte")
        partes_labels = dict(PARTES_POR_TIPO.get(activo.tipo_dispositivo, []))
        estado_partes_items = [
            (partes_labels.get(slug, slug), estado)
            for slug, estado in (ultima.estado_partes or {}).items()
        ]

    return render(request, "mantenimiento/hoja_de_vida.html", {
        "activo": activo,
        "ordenes": ordenes,
        "ultima": ultima,
        "fotos": fotos,
        "equipo_ocs": equipo_ocs,
        "software_ultimo": software_ultimo,
        "acciones_ultimas": acciones_ultimas,
        "estado_partes_items": estado_partes_items,
    })


# ── PDFs ─────────────────────────────────────────────────────────────────────

def _mantenimiento_pdf_bytes(orden):
    import weasyprint

    from django.conf import settings

    html = render_to_string("mantenimiento/orden_pdf.html", {
        "orden": orden,
        "activo": orden.activo,
        "config": ConfiguracionSistema.get_config(),
        "logo_path": os.path.join(settings.BASE_DIR, "static", "img", "logo_redihos_mark.png"),
        "generado": timezone.now(),
    })
    return weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()


@requiere_permiso("mantenimiento", "lectura")
def orden_pdf(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    pdf_bytes = _mantenimiento_pdf_bytes(orden)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    filename = f"mantenimiento_orden_{orden.pk}_{orden.activo.serial}.pdf"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@requiere_permiso("mantenimiento", "lectura")
def reporte_mantenimientos_pdf(request):
    import weasyprint

    from django.conf import settings

    tipo = request.GET.get("tipo", "").strip()
    estado = request.GET.get("estado", "").strip()
    inicio = request.GET.get("inicio", "").strip()
    fin = request.GET.get("fin", "").strip()

    qs = (
        OrdenMantenimiento.objects.select_related("activo")
        .order_by("-fecha_apertura", "-fecha_creacion")
    )
    if tipo:
        qs = qs.filter(tipo=tipo)
    if estado:
        qs = qs.filter(estado=estado)
    if inicio:
        from datetime import datetime as _dt
        try:
            qs = qs.filter(fecha_apertura__gte=_dt.strptime(inicio, "%Y-%m-%d").date())
        except ValueError:
            pass
    if fin:
        from datetime import datetime as _dt
        try:
            qs = qs.filter(fecha_apertura__lte=_dt.strptime(fin, "%Y-%m-%d").date())
        except ValueError:
            pass

    html = render_to_string("mantenimiento/reporte_mantenimientos_pdf.html", {
        "ordenes": qs,
        "config": ConfiguracionSistema.get_config(),
        "logo_path": os.path.join(settings.BASE_DIR, "static", "img", "logo_redihos_mark.png"),
        "generado": timezone.now(),
        "filtro_tipo": tipo,
        "filtro_estado": estado,
        "filtro_inicio": inicio,
        "filtro_fin": fin,
    })
    pdf_bytes = weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="reporte_mantenimientos.pdf"'
    return response
