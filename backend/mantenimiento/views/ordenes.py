"""Órdenes de mantenimiento: lista, detalle, alta, edición y baja, con sus repuestos y fotos.

El cierre y la reapertura están en ``views/ejecucion.py``.
"""

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import CharField, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, Concat
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permisos import requiere_permiso
from inventario.models import Activo

from .. import acta
from ..constants import PARTES_POR_TIPO
from ..forms import FotoMantenimientoForm, OrdenForm, RepuestoForm
from ..models import (
    FORMATO_ACTUAL,
    ESTADOS_ORDEN,
    MAX_FOTOS_ACTA,
    PRIORIDADES,
    TIPOS_MANTENIMIENTO,
    FotoMantenimiento,
    OrdenMantenimiento,
    Repuesto,
)
from ..services import snapshot_software_ocs
from .ejecucion import contexto_checklist


FotoFormSet = modelformset_factory(
    FotoMantenimiento, form=FotoMantenimientoForm, extra=3, can_delete=True
)


# El formset de fotos se instancia SIEMPRE con prefix="fotos": la plantilla y
# las validaciones de la vista dependen de ese prefijo (fotos-TOTAL_FORMS...).
def _foto_formset(*args, **kwargs):
    return FotoFormSet(*args, prefix="fotos", **kwargs)


AVISO_CERRADA ="Un mantenimiento cerrado no se modifica. Reábrelo si necesitas cambiarlo."


def _si_esta_cerrada(request, orden):
    """Redirige al detalle con un aviso si la orden está cerrada; si no, None.

    Las fotos y los repuestos de una orden cerrada no cambian: salen en el acta
    que ya se pudo imprimir y firmar.
    """
    if orden.estado == "cerrada":
        messages.warning(request, AVISO_CERRADA)
        return redirect("mantenimiento:detalle_orden", pk=orden.pk)
    return None


@requiere_permiso("mantenimiento", "lectura")
def lista_ordenes(request):
    qs = OrdenMantenimiento.objects.select_related("activo", "tecnico")

    tipo = request.GET.get("tipo", "").strip()
    estado = request.GET.get("estado", "").strip()
    prioridad = request.GET.get("prioridad", "").strip()
    q = request.GET.get("q", "").strip()
    fallas = request.GET.get("fallas") == "1"

    if fallas:
        qs = qs.filter(tipo="correctivo", estado__in=["reportada", "abierta", "en_proceso"])
    if tipo:
        qs = qs.filter(tipo=tipo)
    if estado:
        qs = qs.filter(estado=estado)
    if prioridad:
        qs = qs.filter(prioridad=prioridad)
    if q:
        # El nombre completo se arma en la consulta: buscar "Nombre Apellido" no
        # encontraba nada, porque first_name y last_name se miraban por separado.
        qs = qs.annotate(
            nombre_del_tecnico=Concat(
                Coalesce("tecnico__first_name", Value("")),
                Value(" "),
                Coalesce("tecnico__last_name", Value("")),
                output_field=CharField(),
            )
        ).filter(
            Q(activo__serial__icontains=q)
            | Q(activo__marca__icontains=q)
            | Q(activo__modelo__icontains=q)
            | Q(tecnico_asignado__icontains=q)
            | Q(nombre_del_tecnico__icontains=q)
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
        "fallas": fallas,
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
    # Las fotos que lleva el acta; en una orden cerrada se muestran sin interruptor.
    ids_fotos_acta = {f.pk for f in acta.fotos_acta(orden)} if orden.formato == FORMATO_ACTUAL else set()

    # El estado de partes solo existe en las órdenes del formato anterior (solo lectura).
    estado_partes_items = []
    if orden.formato != FORMATO_ACTUAL:
        partes_labels = dict(PARTES_POR_TIPO.get(orden.activo.tipo_dispositivo, []))
        estado_partes_items = [
            (partes_labels.get(slug, slug), estado)
            for slug, estado in (orden.estado_partes or {}).items()
        ]

    contexto_extra = (
        contexto_checklist(orden)
        if orden.formato == FORMATO_ACTUAL and orden.tipo == "preventivo"
        else {}
    )

    return render(request, "mantenimiento/detalle_orden.html", {
        **contexto_extra,
        "orden": orden,
        "repuestos": repuestos,
        "repuestos_total": repuestos_total.get("total") or 0,
        "fotos": fotos,
        "ids_fotos_acta": ids_fotos_acta,
        "max_fotos_acta": MAX_FOTOS_ACTA,
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
        form = OrdenForm(request.POST)
        if form.is_valid() and fset_valid:
            # Snapshot automático de software desde OCS si el textarea quedó vacío
            if not form.cleaned_data.get("software_snapshot_text"):
                activo = form.cleaned_data.get("activo")
                if activo:
                    software = snapshot_software_ocs(activo)
                    if software:
                        form.cleaned_data["software_snapshot_text"] = [
                            s.get("name") for s in software if s.get("name")
                        ]
            # Un correctivo nuevo: sin checklist, y solo se cierra por el cierre.
            form.instance.tipo = "correctivo"
            form.instance.estado = "abierta"
            form.instance.formato = FORMATO_ACTUAL
            orden = form.save()
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
        if activo_pk:
            activo = get_object_or_404(Activo, pk=activo_pk)
            software = snapshot_software_ocs(activo)
            initial.update({
                "activo": activo,
                "software_snapshot_text": "\n".join(
                    s["name"] for s in software if s.get("name")
                ),
            })
        form = OrdenForm(initial=initial)
        fset = _foto_formset(queryset=FotoMantenimiento.objects.none())

    return render(request, "mantenimiento/form_correctivo.html", {
        "form": form,
        "fset": fset,
        "titulo": "Documentar mantenimiento",
    })


@requiere_permiso("mantenimiento", "escritura")
def editar_orden(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    if orden.estado == "cerrada":
        messages.warning(request, "Un mantenimiento cerrado no se edita. Reábrelo para hacer cambios.")
        return redirect("mantenimiento:detalle_orden", pk=orden.pk)
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
        form = OrdenForm(request.POST, instance=orden)
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
        form = OrdenForm(instance=orden)
        fset = _foto_formset(queryset=orden.fotos.all())

    return render(request, "mantenimiento/form_correctivo.html", {
        "form": form,
        "fset": fset,
        "titulo": "Editar mantenimiento",
        "orden": orden,
    })


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
    if bloqueo := _si_esta_cerrada(request, orden):
        return bloqueo
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
    repuesto = get_object_or_404(Repuesto.objects.select_related("orden"), pk=pk)
    orden = repuesto.orden
    if bloqueo := _si_esta_cerrada(request, orden):
        return bloqueo
    if request.method == "POST":
        form = RepuestoForm(request.POST, instance=repuesto)
        if form.is_valid():
            # El repuesto no cambia de orden (el campo va oculto): así tampoco
            # se cuela en una orden cerrada.
            repuesto = form.save(commit=False)
            repuesto.orden = orden
            repuesto.save()
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
    repuesto = get_object_or_404(Repuesto.objects.select_related("orden"), pk=pk)
    orden_id = repuesto.orden_id
    if bloqueo := _si_esta_cerrada(request, repuesto.orden):
        return bloqueo
    if request.method == "POST":
        repuesto.delete()
        messages.success(request, "Repuesto eliminado.")
        return redirect("mantenimiento:detalle_orden", pk=orden_id)
    return redirect("mantenimiento:detalle_orden", pk=orden_id)


@requiere_permiso("mantenimiento", "escritura")
def crear_foto(request, pk):
    orden = get_object_or_404(OrdenMantenimiento, pk=pk)
    if bloqueo := _si_esta_cerrada(request, orden):
        return bloqueo
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
    foto = get_object_or_404(FotoMantenimiento.objects.select_related("orden"), pk=pk)
    orden_pk = foto.orden_id
    if bloqueo := _si_esta_cerrada(request, foto.orden):
        return bloqueo
    if request.method == "POST":
        foto.delete()
        messages.success(request, "Foto eliminada.")
    return redirect("mantenimiento:detalle_orden", pk=orden_pk)


@requiere_permiso("mantenimiento", "escritura")
@require_POST
def toggle_foto_acta(request, pk):
    """Marca o desmarca una foto para el acta (hasta MAX_FOTOS_ACTA por orden)."""
    foto = get_object_or_404(FotoMantenimiento.objects.select_related("orden"), pk=pk)
    orden = foto.orden
    if bloqueo := _si_esta_cerrada(request, orden):
        return bloqueo
    with transaction.atomic():
        # Bloquea la orden: dos marcas a la vez no pasan del máximo.
        OrdenMantenimiento.objects.select_for_update().filter(pk=orden.pk).first()
        foto.refresh_from_db(fields=["en_acta"])
        if not foto.en_acta and orden.fotos.filter(en_acta=True).count() >= MAX_FOTOS_ACTA:
            messages.warning(request, f"Solo caben {MAX_FOTOS_ACTA} fotos en el acta.")
        else:
            foto.en_acta = not foto.en_acta
            foto.save(update_fields=["en_acta"])
    return redirect("mantenimiento:detalle_orden", pk=orden.pk)
