"""Editor de checklists: uno por tipo de equipo, con sus puntos."""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permisos import requiere_permiso

from ..forms import PlantillaChecklistForm, PuntoPlantillaFormSet
from ..models import SECCIONES_SUGERIDAS, PlantillaChecklist

PREFIJO_PUNTOS = "puntos"


@requiere_permiso("mantenimiento", "lectura")
def lista_plantillas(request):
    plantillas = PlantillaChecklist.objects.annotate(total_puntos=Count("puntos"))
    return render(request, "mantenimiento/plantillas.html", {"plantillas": plantillas})


def _formulario(request, plantilla, titulo):
    nueva = plantilla is None
    instancia = PlantillaChecklist() if nueva else plantilla
    if request.method == "POST":
        form = PlantillaChecklistForm(request.POST, instance=instancia)
        fset = PuntoPlantillaFormSet(request.POST, instance=instancia, prefix=PREFIJO_PUNTOS)
        if form.is_valid() and fset.is_valid():
            with transaction.atomic():
                guardada = form.save()
                fset.instance = guardada
                fset.save()
            messages.success(request, "Checklist guardado.")
            if nueva:
                return redirect("mantenimiento:editar_plantilla", pk=guardada.pk)
            return redirect("mantenimiento:lista_plantillas")
    else:
        form = PlantillaChecklistForm(instance=instancia)
        fset = PuntoPlantillaFormSet(instance=instancia, prefix=PREFIJO_PUNTOS)
    contexto = {
        "form": form,
        "fset": fset,
        "plantilla": plantilla,
        "titulo": titulo,
        "secciones": SECCIONES_SUGERIDAS,
    }
    return render(request, "mantenimiento/plantilla_form.html", contexto)


@requiere_permiso("mantenimiento", "escritura")
def crear_plantilla(request):
    return _formulario(request, None, "Nuevo checklist")


@requiere_permiso("mantenimiento", "escritura")
def editar_plantilla(request, pk):
    plantilla = get_object_or_404(PlantillaChecklist, pk=pk)
    return _formulario(request, plantilla, f"Checklist · {plantilla.get_tipo_dispositivo_display()}")
