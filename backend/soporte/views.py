from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.permisos import requiere_permiso
from mantenimiento.models import OrdenMantenimiento
from notificaciones.services import aviso_usuario

from .forms import EscalarTicketForm, TicketForm
from .models import ESTADOS_TICKET, PRIORIDADES_TICKET, Ticket


@requiere_permiso("soporte", "lectura")
def lista_tickets(request):
    qs = Ticket.objects.select_related("solicitante", "asignado_a")

    estado = request.GET.get("estado", "").strip()
    prioridad = request.GET.get("prioridad", "").strip()
    q = request.GET.get("q", "").strip()

    if estado:
        qs = qs.filter(estado=estado)
    if prioridad:
        qs = qs.filter(prioridad=prioridad)
    if q:
        qs = qs.filter(
            Q(asunto__icontains=q) | Q(solicitante__username__icontains=q)
        )

    stats = {
        "total": qs.count(),
        "abiertos": qs.filter(estado="abierto").count(),
        "en_proceso": qs.filter(estado="en_proceso").count(),
        "resueltos": qs.filter(estado__in=["resuelto", "cerrado", "escalado"]).count(),
    }

    context = {
        "tickets": qs,
        "filtro_estado": estado,
        "filtro_prioridad": prioridad,
        "filtro_q": q,
        "stats": stats,
        "estados": ESTADOS_TICKET,
        "prioridades": PRIORIDADES_TICKET,
    }
    return render(request, "soporte/lista_tickets.html", context)


@login_required
def crear_ticket(request):
    if request.method == "POST":
        form = TicketForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.solicitante = request.user
            ticket.save()
            messages.success(request, "Ticket creado correctamente.")
            return redirect("soporte:detalle", pk=ticket.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = TicketForm()

    return render(request, "soporte/form_ticket.html", {
        "form": form,
        "titulo": "Nuevo ticket",
    })


@requiere_permiso("soporte", "lectura")
def detalle_ticket(request, pk):
    ticket = get_object_or_404(
        Ticket.objects.select_related("solicitante", "asignado_a"), pk=pk
    )
    asignables = get_user_model().objects.filter(is_active=True).order_by("username")
    return render(request, "soporte/detalle_ticket.html", {
        "ticket": ticket,
        "asignables": asignables,
    })


@requiere_permiso("soporte", "escritura")
def editar_ticket(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == "POST":
        form = TicketForm(request.POST, instance=ticket)
        if form.is_valid():
            ticket = form.save()
            messages.success(request, "Ticket actualizado.")
            return redirect("soporte:detalle", pk=ticket.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = TicketForm(instance=ticket)

    return render(request, "soporte/form_ticket.html", {
        "form": form,
        "titulo": f"Editar ticket #{ticket.pk}",
        "ticket": ticket,
    })


@requiere_permiso("soporte", "escritura")
def asignar_ticket(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == "POST":
        user_id = request.POST.get("asignado_a", "").strip()
        user = None
        if user_id:
            user = get_object_or_404(get_user_model(), pk=user_id)
        ticket.asignado_a = user
        if ticket.estado == "abierto":
            ticket.estado = "en_proceso"
        ticket.save(update_fields=["asignado_a", "estado", "fecha_actualizacion"])
        if user:
            aviso_usuario(
                user,
                f"Ticket asignado · #{ticket.pk}",
                f"Te asignaron el ticket \"{ticket.asunto}\".",
                link=reverse("soporte:detalle", args=[ticket.pk]),
                objetokey=f"ticket:{ticket.pk}",
            )
            messages.success(request, f"Ticket asignado a {user.username}.")
        else:
            messages.success(request, "El ticket quedó sin asignación.")
    return redirect("soporte:detalle", pk=ticket.pk)


@requiere_permiso("soporte", "escritura")
def cambiar_estado(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == "POST":
        nuevo = request.POST.get("estado", "")
        if nuevo in dict(ESTADOS_TICKET):
            ticket.estado = nuevo
            ticket.save(update_fields=["estado", "fecha_actualizacion"])
            messages.success(request, f"Ticket marcado como {dict(ESTADOS_TICKET)[nuevo]}.")
    return redirect("soporte:detalle", pk=ticket.pk)


@requiere_permiso("soporte", "escritura")
def escalar_ticket(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    escalado = ticket.ordenes.first()
    if escalado:
        messages.info(request, "Este ticket ya fue escalado.")
        return redirect("mantenimiento:detalle_orden", pk=escalado.pk)

    if request.method == "POST":
        form = EscalarTicketForm(request.POST, initial={"prioridad": ticket.prioridad})
        if form.is_valid():
            orden = OrdenMantenimiento.objects.create(
                ticket=ticket,
                activo=form.cleaned_data["activo"],
                tipo="correctivo",
                estado="abierta",
                prioridad=form.cleaned_data["prioridad"],
                tecnico_asignado=form.cleaned_data["tecnico_asignado"],
                descripcion=f"Escalado desde ticket #{ticket.pk}: {ticket.asunto}",
            )
            ticket.estado = "escalado"
            ticket.save(update_fields=["estado", "fecha_actualizacion"])
            messages.success(request, "Ticket escalado a orden de mantenimiento.")
            return redirect("mantenimiento:detalle_orden", pk=orden.pk)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = EscalarTicketForm(initial={"prioridad": ticket.prioridad})

    return render(request, "soporte/form_escalar.html", {
        "form": form,
        "ticket": ticket,
    })