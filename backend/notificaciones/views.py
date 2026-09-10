from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Notificacion
from .services import generar_notificaciones


@login_required
def lista_notificaciones(request):
    generar_notificaciones(request.user)
    no_leidas = request.user.notificaciones.filter(leida=False)
    leidas = request.user.notificaciones.filter(leida=True)[:50]
    ctx = {
        "no_leidas": no_leidas,
        "leidas": leidas,
        "total_no_leidas": no_leidas.count(),
    }
    return render(request, "notificaciones/lista.html", ctx)


@login_required
def cantidad(request):
    generar_notificaciones(request.user)
    count = request.user.notificaciones.filter(leida=False).count()
    return render(request, "notificaciones/partials/campana.html", {"count": count})


@login_required
def marcar_leida(request, pk):
    notif = get_object_or_404(Notificacion, pk=pk, usuario=request.user)
    if request.method == "POST":
        notif.leida = True
        notif.save(update_fields=["leida"])
    return redirect("notificaciones:lista")


@login_required
def marcar_todas_leidas(request):
    if request.method == "POST":
        request.user.notificaciones.filter(leida=False).update(leida=True)
    return redirect("notificaciones:lista")