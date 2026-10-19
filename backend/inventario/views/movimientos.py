"""Movimientos de activos (asignar, devolver, trasladar) y actas."""


import logging

from django.contrib import messages
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone


from notificaciones.services import encolar_email

from ..forms import (
    AsignacionForm,
    DevolucionForm, TrasladoForm, SubirActaForm,
)
from ..models import (
    Activo, Asignacion, Movimiento, ActaAsignacion,
)
from ..services import acta_pdf_bytes

from accounts.permisos import requiere_permiso, tiene_permiso

logger = logging.getLogger(__name__)



# ── Movimientos ───────────────────────────────────────────────────────────────

@requiere_permiso("inventario", "escritura")
def asignar_activo(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    if activo.estado != "disponible":
        messages.error(request, "Solo se pueden asignar activos disponibles.")
        return redirect("inventario:detalle", pk=activo.pk)

    if request.method == "POST":
        form = AsignacionForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                activo = Activo.objects.select_for_update().get(pk=pk)
                if activo.estado != "disponible":
                    messages.error(request, "Solo se pueden asignar activos disponibles.")
                    return redirect("inventario:detalle", pk=activo.pk)
                asignacion = form.save(commit=False)
                asignacion.activo = activo
                asignacion.fecha_asignacion = timezone.now().date()
                asignacion.save()

                Movimiento.objects.create(
                    activo=activo,
                    tipo="asignacion",
                    fecha=timezone.now().date(),
                    descripcion=f"Asignado a {asignacion.usuario.nombre_completo}. {asignacion.observaciones or ''}",
                    realizado_por=request.user.username if request.user.is_authenticated else "Sistema",
                    usuario_destino=asignacion.usuario
                )

                acta = ActaAsignacion.objects.create(asignacion=asignacion)
                encolar_email(
                    asignacion.usuario.correo,
                    f"Acta de asignación #{acta.pk} · {activo.serial}",
                    f"Hola {asignacion.usuario.nombre_completo},\n"
                    f"te asignamos el activo {activo.marca} {activo.modelo} "
                    f"(serial {activo.serial}).\n"
                    f"Adjuntamos el acta para que la firmes y la reenvíes a Sistemas.",
                    adjunto_tipo="acta",
                    adjunto_objeto_id=acta.pk,
                )

                activo.estado = "asignado"
                activo.save(update_fields=["estado", "fecha_actualizacion"])

            messages.success(request, f"Activo asignado a {asignacion.usuario.nombre_completo}.")
            return redirect("inventario:detalle", pk=activo.pk)
    else:
        form = AsignacionForm()

    return render(request, "inventario/asignacion_form.html", {
        "form": form, "titulo": "Asignar Activo", "activo": activo, "accion": "Asignar"
    })

@requiere_permiso("inventario", "escritura")
def editar_asignacion(request, asignacion_pk):
    asignacion = get_object_or_404(Asignacion, pk=asignacion_pk)
    activo = asignacion.activo
    if request.method == "POST":
        form = AsignacionForm(request.POST, instance=asignacion)
        if form.is_valid():
            form.save()
            messages.success(request, "Datos de entrega actualizados.")
            return redirect("inventario:detalle", pk=activo.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = AsignacionForm(instance=asignacion)

    return render(request, "inventario/asignacion_form.html", {
        "form": form, "titulo": "Datos de entrega", "activo": activo, "accion": "Entrega",
    })


@requiere_permiso("inventario", "escritura")
def devolver_activo(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    asignacion = activo.asignaciones.filter(activa=True).first()

    if not asignacion:
        messages.error(request, "El activo no tiene una asignación activa.")
        return redirect("inventario:detalle", pk=activo.pk)

    if request.method == "POST":
        form = DevolucionForm(request.POST)
        if form.is_valid():
            observaciones = form.cleaned_data["observaciones"]
            with transaction.atomic():
                activo = Activo.objects.select_for_update().get(pk=pk)
                asignacion = activo.asignaciones.filter(activa=True).first()
                if not asignacion:
                    messages.error(request, "El activo no tiene una asignación activa.")
                    return redirect("inventario:detalle", pk=activo.pk)
                asignacion.activa = False
                asignacion.fecha_devolucion = timezone.now().date()
                if observaciones:
                    asignacion.observaciones = (asignacion.observaciones or "") + f"\n[Devolución]: {observaciones}"
                asignacion.save()

                Movimiento.objects.create(
                    activo=activo,
                    tipo="devolucion",
                    fecha=timezone.now().date(),
                    descripcion=f"Devuelto por {asignacion.usuario.nombre_completo}. {observaciones}",
                    realizado_por=request.user.username if request.user.is_authenticated else "Sistema"
                )

                activo.estado = "disponible"
                activo.save(update_fields=["estado", "fecha_actualizacion"])

            messages.success(request, "Activo devuelto correctamente.")
            return redirect("inventario:detalle", pk=activo.pk)
    else:
        form = DevolucionForm()

    return render(request, "inventario/asignacion_form.html", {
        "form": form, "titulo": "Devolver Activo", "activo": activo, "accion": "Devolver"
    })

@requiere_permiso("inventario", "escritura")
def trasladar_activo(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    asignacion_actual = activo.asignaciones.filter(activa=True).first()

    if not asignacion_actual:
        messages.error(request, "El activo no está asignado actualmente.")
        return redirect("inventario:detalle", pk=activo.pk)

    if request.method == "POST":
        form = TrasladoForm(request.POST)
        if form.is_valid():
            usuario_destino = form.cleaned_data["usuario_destino"]
            observaciones = form.cleaned_data["observaciones"]

            if usuario_destino == asignacion_actual.usuario:
                messages.error(request, "El usuario destino debe ser diferente al actual.")
                return render(request, "inventario/asignacion_form.html", {
                    "form": form, "titulo": "Trasladar Activo", "activo": activo, "accion": "Trasladar"
                })

            with transaction.atomic():
                activo = Activo.objects.select_for_update().get(pk=pk)
                asignacion_actual = activo.asignaciones.filter(activa=True).first()
                if not asignacion_actual:
                    messages.error(request, "El activo no está asignado actualmente.")
                    return redirect("inventario:detalle", pk=activo.pk)
                if usuario_destino == asignacion_actual.usuario:
                    messages.error(request, "El usuario destino debe ser diferente al actual.")
                    return render(request, "inventario/asignacion_form.html", {
                        "form": form, "titulo": "Trasladar Activo", "activo": activo, "accion": "Trasladar"
                    })
                # 1. Cerrar asignación actual
                asignacion_actual.activa = False
                asignacion_actual.fecha_devolucion = timezone.now().date()
                if observaciones:
                    asignacion_actual.observaciones = (asignacion_actual.observaciones or "") + f"\n[Traslado a {usuario_destino.nombre_completo}]: {observaciones}"
                asignacion_actual.save()

                # 2. Crear nueva asignación
                nueva_asignacion = Asignacion.objects.create(
                    activo=activo,
                    usuario=usuario_destino,
                    fecha_asignacion=timezone.now().date(),
                    observaciones=f"Trasladado desde {asignacion_actual.usuario.nombre_completo}. {observaciones}"
                )

                # 3. Registrar movimiento
                Movimiento.objects.create(
                    activo=activo,
                    tipo="traslado",
                    fecha=timezone.now().date(),
                    descripcion=f"Trasladado de {asignacion_actual.usuario.nombre_completo} a {usuario_destino.nombre_completo}. {observaciones}",
                    realizado_por=request.user.username if request.user.is_authenticated else "Sistema",
                    usuario_destino=usuario_destino
                )

                acta = ActaAsignacion.objects.create(asignacion=nueva_asignacion)
                encolar_email(
                    usuario_destino.correo,
                    f"Acta de asignación #{acta.pk} · {activo.serial}",
                    f"Hola {usuario_destino.nombre_completo},\n"
                    f"te fue trasladado el activo {activo.marca} {activo.modelo} "
                    f"(serial {activo.serial}).\n"
                    f"Adjuntamos el acta para que la firmes y la reenvíes a Sistemas.",
                    adjunto_tipo="acta",
                    adjunto_objeto_id=acta.pk,
                )
                activo.estado = "asignado"
                activo.save(update_fields=["estado", "fecha_actualizacion"])

            messages.success(request, f"Activo trasladado a {usuario_destino.nombre_completo}.")
            return redirect("inventario:detalle", pk=activo.pk)
    else:
        form = TrasladoForm()

    return render(request, "inventario/asignacion_form.html", {
        "form": form, "titulo": "Trasladar Activo", "activo": activo, "accion": "Trasladar"
    })

# ── Actas PDF ──────────────────────────────────────────────────────────────────

@requiere_permiso("inventario", "lectura")
def generar_acta_pdf(request, asignacion_pk):
    asignacion = get_object_or_404(Asignacion, pk=asignacion_pk)

    pdf_bytes = acta_pdf_bytes(asignacion)

    # ── Persist PDF in ActaAsignacion if not already saved ─────────────────
    # Solo quien puede escribir en inventario deja el PDF guardado; un
    # usuario de lectura lo ve generado al vuelo sin tocar el disco.
    acta = getattr(asignacion, "acta", None)
    if acta and not acta.pdf_generado and tiene_permiso(request.user, "inventario", "escritura"):
        filename = f"acta_{asignacion.activo.serial}_{asignacion.usuario.documento_identidad}.pdf"
        acta.pdf_generado.save(filename, ContentFile(pdf_bytes), save=True)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="acta_{asignacion.activo.serial}'
        f'_{asignacion.usuario.documento_identidad}.pdf"'
    )
    return response



@requiere_permiso("inventario", "escritura")
def subir_acta_firmada(request, asignacion_pk):
    asignacion = get_object_or_404(Asignacion, pk=asignacion_pk)
    acta = getattr(asignacion, "acta", None)

    if not acta:
        messages.error(request, "No existe registro de acta para esta asignación.")
        return redirect("inventario:detalle", pk=asignacion.activo.pk)

    if request.method == "POST":
        form = SubirActaForm(request.POST, request.FILES)
        if form.is_valid():
            acta.escaneado_firmado = form.cleaned_data["escaneado_firmado"]
            acta.save()
            messages.success(request, "Acta firmada subida correctamente.")
            return redirect("inventario:detalle", pk=asignacion.activo.pk)
    else:
        form = SubirActaForm()

    return render(request, "inventario/asignacion_form.html", {
        "form": form,
        "titulo": "Subir Acta Firmada",
        "activo": asignacion.activo,
        "accion": "Subir",
    })
