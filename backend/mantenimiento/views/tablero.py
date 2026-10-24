"""Pantalla principal de mantenimiento: qué equipos tocan y programar su fecha."""

from django.contrib import messages
from django.db.models import Prefetch, prefetch_related_objects
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.permisos import requiere_permiso
from inventario.models import Activo, Asignacion

from .. import programacion
from ..forms import ProgramarForm
from ..models import OrdenMantenimiento, ProgramacionMantenimiento

PESTANAS = ("por_hacer", "en_garantia", "al_dia")


def _pestana(valor):
    return valor if valor in PESTANAS else "por_hacer"


def _contar_fallas():
    return OrdenMantenimiento.objects.filter(
        tipo="correctivo", estado__in=["reportada", "abierta", "en_proceso"]
    ).count()


def _contexto(tab, error=None):
    """Datos de la pantalla: tarjetas, pestañas y las filas de la pestaña activa."""
    datos = programacion.tablero()
    filas = datos[tab]
    # Una sola consulta para los responsables de todas las filas.
    prefetch_related_objects(
        [s.activo for s in filas],
        Prefetch(
            "asignaciones",
            queryset=Asignacion.objects.filter(activa=True).select_related("usuario"),
            to_attr="asignaciones_activas",
        ),
    )
    # La situación es inmutable: cada fila lleva su responsable aparte.
    filas = [
        {"s": s, "responsable": s.activo.asignaciones_activas[0].usuario if s.activo.asignaciones_activas else None}
        for s in filas
    ]
    return {
        "tab": tab,
        "filas": filas,
        "conteos": datos["conteos"],
        "totales": {t: len(datos[t]) for t in PESTANAS},
        "fallas": _contar_fallas(),
        "error": error,
    }


@requiere_permiso("mantenimiento", "lectura")
def inicio(request):
    return render(request, "mantenimiento/inicio.html", _contexto(_pestana(request.GET.get("tab"))))


@requiere_permiso("mantenimiento", "escritura")
@require_POST
def programar(request, activo_pk):
    activo = get_object_or_404(Activo, pk=activo_pk)
    tab = _pestana(request.POST.get("tab"))
    form = ProgramarForm(request.POST)
    error = None
    if form.is_valid():
        fecha = form.cleaned_data["fecha_programada"]
        if fecha is not None:
            ProgramacionMantenimiento.objects.update_or_create(activo=activo, defaults={"fecha_programada": fecha})
        else:
            ProgramacionMantenimiento.objects.filter(activo=activo).update(fecha_programada=None)
    else:
        error = " ".join(form.errors["fecha_programada"])
    if request.htmx:
        return render(request, "mantenimiento/partials/tabla_programacion.html", _contexto(tab, error))
    if error:
        messages.error(request, error)
    return redirect(f"{reverse('mantenimiento:inicio')}?tab={tab}")
