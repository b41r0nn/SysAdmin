from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string

from accounts.permisos import requiere_permiso

from .forms import ConfiguracionForm, CuentaForm, CuentaRolForm
from .models import ConfiguracionSistema, RegistroAuditoria

CustomUser = get_user_model()


def _password_temporal():
    return get_random_string(length=12)


@requiere_permiso("administracion", "lectura")
def lista_auditoria(request):
    qs = RegistroAuditoria.objects.select_related("usuario").all()

    modulo = request.GET.get("modulo", "").strip()
    accion = request.GET.get("accion", "").strip()
    q = request.GET.get("q", "").strip()

    if modulo:
        qs = qs.filter(modulo=modulo)
    if accion:
        qs = qs.filter(accion=accion)
    if q:
        qs = qs.filter(
            Q(detalle__icontains=q)
            | Q(objeto_tipo__icontains=q)
            | Q(usuario__username__icontains=q)
        )

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page", 1))

    acciones = (
        RegistroAuditoria.objects.values_list("accion", flat=True)
        .distinct()
        .order_by("accion")
    )

    return render(request, "administracion/auditoria_lista.html", {
        "registros": page,
        "modulos": [("", "Todos los módulos")] + list(RegistroAuditoria._meta.get_field("modulo").choices),
        "acciones": acciones,
        "filtro_modulo": modulo,
        "filtro_accion": accion,
        "filtro_q": q,
    })


@requiere_permiso("administracion", "escritura")
def configuracion(request):
    config = ConfiguracionSistema.get_config()

    if request.method == "POST":
        form = ConfiguracionForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuración del sistema actualizada.")
            return redirect("administracion:configuracion")
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = ConfiguracionForm(instance=config)

    return render(request, "administracion/configuracion_form.html", {
        "form": form,
        "config": config,
    })


@requiere_permiso("administracion", "lectura")
def lista_cuentas(request):
    q = request.GET.get("q", "").strip()
    qs = CustomUser.objects.order_by("username")
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))

    context = {
        "cuentas": qs,
        "q": q,
        "total": qs.count(),
        "activas": qs.filter(is_active=True).count(),
    }
    if request.headers.get("HX-Request"):
        return render(request, "administracion/partials/tabla_cuentas.html", context)
    return render(request, "administracion/cuentas_lista.html", context)


@requiere_permiso("administracion", "escritura")
def crear_cuenta(request):
    if request.method == "POST":
        form = CuentaForm(request.POST)
        if form.is_valid():
            cuenta = form.save(commit=False)
            password_temporal = _password_temporal()
            cuenta.set_password(password_temporal)
            cuenta.is_superuser = cuenta.rol == "superadmin"
            cuenta.is_staff = cuenta.rol == "superadmin"
            cuenta.save()
            messages.success(
                request,
                f"Cuenta «{cuenta.username}» creada. Contraseña temporal: {password_temporal} "
                "(se muestra una sola vez).",
            )
            return redirect("administracion:cuentas")
    else:
        form = CuentaForm()
    return render(request, "administracion/cuenta_form.html", {"form": form})


@requiere_permiso("administracion", "escritura")
def cambiar_rol_cuenta(request, pk):
    cuenta = get_object_or_404(CustomUser, pk=pk)
    if request.method == "POST":
        form = CuentaRolForm(request.POST, instance=cuenta)
        if form.is_valid():
            nuevo_rol = form.cleaned_data["rol"]
            if cuenta.pk == request.user.pk and nuevo_rol != "superadmin":
                messages.error(request, "No puedes quitarte el rol Super Administrador a ti mismo.")
            else:
                cuenta.rol = nuevo_rol
                cuenta.is_superuser = nuevo_rol == "superadmin"
                cuenta.is_staff = nuevo_rol == "superadmin"
                cuenta.save(update_fields=["rol", "is_superuser", "is_staff"])
                messages.success(
                    request,
                    f"Rol de «{cuenta.username}» actualizado a {cuenta.get_rol_display()}.",
                )
                return redirect("administracion:cuentas")
    else:
        form = CuentaRolForm(instance=cuenta)
    return render(request, "administracion/cuenta_rol.html", {"form": form, "cuenta": cuenta})


@requiere_permiso("administracion", "escritura")
def toggle_cuenta(request, pk):
    cuenta = get_object_or_404(CustomUser, pk=pk)
    if request.method == "POST":
        if cuenta.pk == request.user.pk:
            messages.error(request, "No puedes desactivar tu propia cuenta.")
        else:
            cuenta.is_active = not cuenta.is_active
            cuenta.save(update_fields=["is_active"])
            if cuenta.is_active:
                messages.success(request, f"Cuenta «{cuenta.username}» activada.")
            else:
                messages.warning(request, f"Cuenta «{cuenta.username}» desactivada.")
    return redirect("administracion:cuentas")


@requiere_permiso("administracion", "escritura")
def resetear_password(request, pk):
    cuenta = get_object_or_404(CustomUser, pk=pk)
    if request.method == "POST":
        password_temporal = _password_temporal()
        cuenta.set_password(password_temporal)
        cuenta.save(update_fields=["password"])
        messages.success(
            request,
            f"Contraseña de «{cuenta.username}» reiniciada. Temporal: {password_temporal} "
            "(se muestra una sola vez).",
        )
    return redirect("administracion:cuentas")