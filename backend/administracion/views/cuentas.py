from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string

from accounts.permisos import requiere_permiso

from ..forms import CuentaForm, CuentaRolForm

CustomUser = get_user_model()


def _password_temporal():
    return get_random_string(length=12)


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
    """Editar una cuenta: nombres, apellidos, cargo y rol."""
    cuenta = get_object_or_404(CustomUser, pk=pk)
    if request.method == "POST":
        form = CuentaRolForm(request.POST, instance=cuenta)
        if form.is_valid():
            nuevo_rol = form.cleaned_data["rol"]
            if cuenta.pk == request.user.pk and nuevo_rol != "superadmin":
                # is_valid() ya copió los datos a la instancia: se vuelve a lo guardado.
                cuenta.refresh_from_db()
                messages.error(request, "No puedes quitarte el rol Super Administrador a ti mismo.")
            else:
                cuenta.rol = nuevo_rol
                cuenta.is_superuser = nuevo_rol == "superadmin"
                cuenta.is_staff = nuevo_rol == "superadmin"
                cuenta.save(
                    update_fields=["first_name", "last_name", "cargo", "rol", "is_superuser", "is_staff"]
                )
                messages.success(
                    request,
                    f"Cuenta «{cuenta.username}» actualizada · rol {cuenta.get_rol_display()}.",
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
