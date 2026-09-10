from datetime import date

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permisos import requiere_permiso

from .forms import PrestamoForm
from .models import ESTADOS_PRESTAMO, Prestamo

BADGES_ESTADO = {
    "activo": "primary",
    "vencido": "danger",
    "devuelto": "success",
}


def _prestamos_filtrados(request):
    qs = Prestamo.objects.select_related("activo", "solicitante")
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "").strip()

    if q:
        qs = qs.filter(
            Q(activo__serial__icontains=q)
            | Q(activo__marca__icontains=q)
            | Q(solicitante__username__icontains=q)
            | Q(destino__icontains=q)
        )

    if estado:
        objetos = [p for p in qs if p.estado == estado]
    else:
        objetos = list(qs)

    return objetos, {"q": q, "estado": estado}


@requiere_permiso("prestamos", "lectura")
def lista(request):
    objetos, filtros = _prestamos_filtrados(request)

    stats = {
        "total": len(objetos),
        "activos": sum(1 for p in objetos if p.estado == "activo"),
        "vencidos": sum(1 for p in objetos if p.estado == "vencido"),
        "devueltos": sum(1 for p in objetos if p.estado == "devuelto"),
    }

    return render(request, "prestamos/lista.html", {
        "prestamos": objetos,
        "filtro_q": filtros["q"],
        "filtro_estado": filtros["estado"],
        "stats": stats,
        "estados": ESTADOS_PRESTAMO,
        "badges_estado": BADGES_ESTADO,
    })


@requiere_permiso("prestamos", "lectura")
def detalle(request, pk):
    prestamo = get_object_or_404(
        Prestamo.objects.select_related("activo", "solicitante"), pk=pk
    )
    return render(request, "prestamos/detalle.html", {
        "prestamo": prestamo,
        "badge_estado": BADGES_ESTADO[prestamo.estado],
    })


@requiere_permiso("prestamos", "escritura")
def crear(request):
    if request.method == "POST":
        form = PrestamoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Préstamo registrado correctamente.")
            return redirect("prestamos:lista")
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = PrestamoForm(initial={"fecha_prestamo": date.today()})

    return render(request, "prestamos/form.html", {
        "form": form,
        "titulo": "Nuevo préstamo",
    })


@requiere_permiso("prestamos", "escritura")
def editar(request, pk):
    prestamo = get_object_or_404(Prestamo, pk=pk)
    if request.method == "POST":
        form = PrestamoForm(request.POST, instance=prestamo)
        if form.is_valid():
            form.save()
            messages.success(request, "Préstamo actualizado.")
            return redirect("prestamos:detalle", pk=prestamo.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = PrestamoForm(instance=prestamo)

    return render(request, "prestamos/form.html", {
        "form": form,
        "titulo": f"Editar préstamo #{prestamo.pk}",
        "prestamo": prestamo,
    })


@requiere_permiso("prestamos", "escritura")
def registrar_devolucion(request, pk):
    prestamo = get_object_or_404(Prestamo, pk=pk)
    if request.method == "POST":
        if prestamo.estado == "devuelto":
            messages.info(request, "Este préstamo ya figura como devuelto.")
        else:
            prestamo.fecha_devolucion = date.today()
            prestamo.save(update_fields=["fecha_devolucion", "fecha_actualizacion"])
            messages.success(request, "Devolución registrada.")
    return redirect("prestamos:detalle", pk=prestamo.pk)