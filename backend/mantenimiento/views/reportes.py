"""Calendario, reporte de fallas, hoja de vida y PDFs de mantenimiento."""

import os

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from accounts.permisos import requiere_permiso
from administracion.models import ConfiguracionSistema
from inventario.models import Activo
from notificaciones.services import aviso_usuario, encolar_email

from ..constants import PARTES_POR_TIPO
from ..forms import ReporteFallaForm
from ..models import FotoMantenimiento, OrdenMantenimiento, PlanMantenimiento
from ..services import hoja_de_vida_pdf_bytes, reporte_activos_pdf_bytes


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


# ── Hoja de vida por activo ──────────────────────────────────────────────────

@requiere_permiso("mantenimiento", "lectura")
def hoja_de_vida_buscar(request):
    """Índice de hoja de vida: búsqueda HTMX por serial/marca/modelo.

    Cuando la petición viene con HX-Request devuelve solo el partial de
    resultados (mismo patrón que lista_planes/lista_ordenes).
    """
    q = request.GET.get("q", "").strip()
    resultados = []
    if q:
        resultados = (
            Activo.objects.filter(
                Q(serial__icontains=q) | Q(marca__icontains=q) | Q(modelo__icontains=q)
            )
            .order_by("tipo_dispositivo", "marca", "modelo")[:50]
        )
    context = {
        "q": q,
        "resultados": resultados,
    }
    if request.headers.get("HX-Request"):
        return render(request, "mantenimiento/partials/resultados_hoja_de_vida.html", context)
    return render(request, "mantenimiento/hoja_de_vida_buscar.html", context)


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
def hoja_de_vida_pdf(request, activo_pk):
    activo = get_object_or_404(Activo, pk=activo_pk)
    pdf_bytes = hoja_de_vida_pdf_bytes(activo)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    filename = f"hoja_de_vida_{activo.serial}.pdf"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@requiere_permiso("mantenimiento", "lectura")
def reporte_activos_pdf(request):
    """Reporte PDF con una fila por activo que tenga al menos un mantenimiento
    hecho (fecha del último mantenimiento cerrado)."""
    pdf_bytes = reporte_activos_pdf_bytes()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = (
        'inline; filename="reporte_activos_con_mantenimiento.pdf"'
    )
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
