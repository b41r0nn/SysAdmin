"""CRUD del catálogo de modelos."""


import logging

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render



from ..forms import (
    CatalogoModeloForm,
)
from ..models import (
    CatalogoModelo,
)

from accounts.permisos import requiere_permiso

logger = logging.getLogger(__name__)



# ══════════════════════════════════════════════════════════════════════════════
# CRUD — CatalogoModelo
# ══════════════════════════════════════════════════════════════════════════════

@requiere_permiso("inventario", "lectura")
def catalogo_json(request):
    """Devuelve modelos de catálogo filtrados por tipo_dispositivo (JSON)."""
    tipo = request.GET.get("tipo", "").strip()
    qs = CatalogoModelo.objects.all()
    if tipo:
        qs = qs.filter(tipo_dispositivo=tipo)
    data = [
        {
            "id": item.pk,
            "text": str(item),
            "marca": item.marca,
            "modelo": item.modelo,
        }
        for item in qs
    ]
    return JsonResponse({"catalogo": data})


@requiere_permiso("inventario", "lectura")
def lista_catalogo(request):
    from ..models import TIPOS
    qs = CatalogoModelo.objects.all()

    tipo = request.GET.get("tipo", "")
    q = request.GET.get("q", "").strip()

    if tipo:
        qs = qs.filter(tipo_dispositivo=tipo)
    if q:
        qs = qs.filter(
            Q(marca__icontains=q) | Q(modelo__icontains=q)
        )

    ctx = {"catalogo": qs, "tipos": TIPOS, "filtro_tipo": tipo, "filtro_q": q}
    return render(request, "inventario/catalogo_lista.html", ctx)


@requiere_permiso("inventario", "escritura")
def crear_catalogo(request):
    if request.method == "POST":
        form = CatalogoModeloForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Modelo de catálogo «{obj}» creado.")
            return redirect("inventario:catalogo_lista")
        else:
            messages.error(request, "Corrige los errores del formulario.")
    else:
        form = CatalogoModeloForm()

    return render(request, "inventario/form.html", {"form": form, "titulo": "Nuevo Modelo de Catálogo"})


@requiere_permiso("inventario", "escritura")
def editar_catalogo(request, pk):
    obj = get_object_or_404(CatalogoModelo, pk=pk)
    if request.method == "POST":
        form = CatalogoModeloForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Modelo de catálogo «{obj}» actualizado.")
            return redirect("inventario:catalogo_lista")
        else:
            messages.error(request, "Corrige los errores del formulario.")
    else:
        form = CatalogoModeloForm(instance=obj)

    return render(request, "inventario/form.html", {"form": form, "titulo": "Editar Modelo de Catálogo"})
