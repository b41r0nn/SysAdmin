from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import Usuario
from .forms import UsuarioForm


@login_required
def lista_usuarios(request):
    q = request.GET.get("q", "").strip()
    area = request.GET.get("area", "").strip()
    estado = request.GET.get("estado", "").strip()

    qs = Usuario.objects.all()

    if q:
        qs = qs.filter(
            Q(nombre_completo__icontains=q) | Q(documento_identidad__icontains=q)
        )
    if area:
        qs = qs.filter(area__icontains=area)
    if estado:
        qs = qs.filter(estado=estado)

    areas = Usuario.objects.values_list("area", flat=True).distinct().order_by("area")

    context = {
        "usuarios": qs,
        "areas": areas,
        "q": q,
        "area_sel": area,
        "estado_sel": estado,
        "total": qs.count(),
        "activos": qs.filter(estado="activo").count(),
        "inactivos": qs.filter(estado="inactivo").count(),
    }

    # HTMX: retorna solo la tabla parcial
    if request.headers.get("HX-Request"):
        return render(request, "usuarios/partials/tabla.html", context)

    return render(request, "usuarios/lista.html", context)


@login_required
def detalle_usuario(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    from inventario.models import Asignacion
    asignaciones = Asignacion.objects.filter(usuario=usuario, activa=True).select_related("activo")
    activos = []
    for asignacion in asignaciones:
        activo = asignacion.activo
        activo.fecha_asignacion = asignacion.fecha_asignacion
        activos.append(activo)
    context = {
        "usuario": usuario,
        "activos": activos,
    }
    return render(request, "usuarios/detalle.html", context)


@login_required
def crear_usuario(request):
    if request.method == "POST":
        form = UsuarioForm(request.POST, request.FILES)
        if form.is_valid():
            usuario = form.save()
            messages.success(request, f"Usuario «{usuario.nombre_completo}» creado correctamente.")
            return redirect("usuarios:detalle", pk=usuario.pk)
    else:
        form = UsuarioForm()

    return render(request, "usuarios/form.html", {"form": form, "titulo": "Nuevo usuario"})


@login_required
def editar_usuario(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == "POST":
        form = UsuarioForm(request.POST, request.FILES, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, f"Usuario «{usuario.nombre_completo}» actualizado.")
            return redirect("usuarios:detalle", pk=usuario.pk)
    else:
        form = UsuarioForm(instance=usuario)

    return render(request, "usuarios/form.html", {
        "form": form,
        "titulo": f"Editar — {usuario.nombre_completo}",
        "usuario": usuario,
    })


@login_required
def toggle_estado_usuario(request, pk):
    """Activa o desactiva un usuario. Nunca se elimina."""
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == "POST":
        if usuario.is_activo:
            usuario.desactivar()
            messages.warning(request, f"Usuario «{usuario.nombre_completo}» desactivado.")
        else:
            usuario.activar()
            messages.success(request, f"Usuario «{usuario.nombre_completo}» activado.")
    return redirect("usuarios:detalle", pk=usuario.pk)
