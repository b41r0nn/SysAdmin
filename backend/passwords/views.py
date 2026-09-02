from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from openpyxl import Workbook

from .forms import CredencialForm, VaultForm
from .models import AccesoLog, Credencial, Vault, ESTADOS_CREDENCIAL


def _is_admin(user):
    return user.is_superuser or user.is_staff


def _require_admin(request):
    if not _is_admin(request.user):
        raise PermissionDenied


def _log_action(vault, usuario, accion, credencial=None, detalle=""):
    AccesoLog.objects.create(
        vault=vault,
        credencial=credencial,
        usuario=usuario,
        accion=accion,
        detalle=detalle,
    )


@login_required
def index(request):
    _require_admin(request)

    vaults = Vault.objects.annotate(total_credenciales=Count("credenciales")).order_by("nombre")
    return render(request, "passwords/index.html", {
        "vaults": vaults,
    })


@login_required
def vault_crear(request):
    _require_admin(request)

    if request.method == "POST":
        form = VaultForm(request.POST)
        if form.is_valid():
            vault = form.save(commit=False)
            if not vault.creado_por_id:
                vault.creado_por = request.user
            vault.save()
            _log_action(vault, request.user, "vault_creado")
            messages.success(request, "Vault creado correctamente.")
            return redirect("passwords:index")
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = VaultForm()

    return render(request, "passwords/vault_form.html", {
        "form": form,
        "titulo": "Nuevo vault",
    })


@login_required
def vault_editar(request, pk):
    _require_admin(request)

    vault = get_object_or_404(Vault, pk=pk)
    if request.method == "POST":
        form = VaultForm(request.POST, instance=vault)
        if form.is_valid():
            form.save()
            _log_action(vault, request.user, "vault_actualizado")
            messages.success(request, "Vault actualizado.")
            return redirect("passwords:index")
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = VaultForm(instance=vault)

    return render(request, "passwords/vault_form.html", {
        "form": form,
        "titulo": "Editar vault",
        "vault": vault,
    })


@login_required
def vault_eliminar(request, pk):
    _require_admin(request)

    vault = get_object_or_404(Vault, pk=pk)
    if request.method == "POST":
        vault.delete()
        _log_action(vault, request.user, "vault_eliminado")
        messages.warning(request, "Vault eliminado.")
        return redirect("passwords:index")

    return render(request, "passwords/confirm_delete.html", {
        "titulo": "Eliminar vault",
        "mensaje": f"Eliminar vault '{vault.nombre}' y todas sus credenciales?",
        "volver_url": "passwords:index",
        "volver_kwargs": {},
    })


@login_required
def credenciales_lista(request, vault_id):
    _require_admin(request)

    vault = get_object_or_404(Vault, pk=vault_id)
    qs = Credencial.objects.filter(vault=vault).order_by("-fecha_creacion")

    estado = request.GET.get("estado", "").strip()
    q = request.GET.get("q", "").strip()
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(
            Q(titulo__icontains=q)
            | Q(usuario__icontains=q)
            | Q(url__icontains=q)
        )

    return render(request, "passwords/credenciales_list.html", {
        "vault": vault,
        "credenciales": qs,
        "filtro_estado": estado,
        "filtro_q": q,
        "estados": ESTADOS_CREDENCIAL,
    })


@login_required
def credencial_crear(request, vault_id):
    _require_admin(request)

    vault = get_object_or_404(Vault, pk=vault_id)
    if request.method == "POST":
        form = CredencialForm(request.POST)
        if form.is_valid():
            credencial = form.save(commit=False)
            credencial.vault = vault
            if not credencial.creado_por_id:
                credencial.creado_por = request.user
            credencial.save()
            _log_action(vault, request.user, "credencial_creada", credencial=credencial)
            messages.success(request, "Credencial creada correctamente.")
            return redirect("passwords:credenciales_lista", vault_id=vault.id)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = CredencialForm()

    return render(request, "passwords/credencial_form.html", {
        "form": form,
        "titulo": "Nueva credencial",
        "vault": vault,
    })


@login_required
def credencial_editar(request, vault_id, pk):
    _require_admin(request)

    vault = get_object_or_404(Vault, pk=vault_id)
    credencial = get_object_or_404(Credencial, pk=pk, vault=vault)
    if request.method == "POST":
        form = CredencialForm(request.POST, instance=credencial)
        if form.is_valid():
            form.save()
            _log_action(vault, request.user, "credencial_actualizada", credencial=credencial)
            messages.success(request, "Credencial actualizada.")
            return redirect("passwords:credenciales_lista", vault_id=vault.id)
        messages.error(request, "Corrige los errores del formulario.")
    else:
        form = CredencialForm(instance=credencial)

    return render(request, "passwords/credencial_form.html", {
        "form": form,
        "titulo": "Editar credencial",
        "vault": vault,
        "credencial": credencial,
    })


@login_required
def credencial_eliminar(request, vault_id, pk):
    _require_admin(request)

    vault = get_object_or_404(Vault, pk=vault_id)
    credencial = get_object_or_404(Credencial, pk=pk, vault=vault)
    if request.method == "POST":
        credencial.delete()
        _log_action(vault, request.user, "credencial_eliminada", credencial=credencial)
        messages.warning(request, "Credencial eliminada.")
        return redirect("passwords:credenciales_lista", vault_id=vault.id)

    return render(request, "passwords/confirm_delete.html", {
        "titulo": "Eliminar credencial",
        "mensaje": f"Eliminar credencial '{credencial.titulo}'?",
        "volver_url": "passwords:credenciales_lista",
        "volver_kwargs": {"vault_id": vault.id},
    })


@login_required
def credencial_secreto(request, vault_id, pk):
    _require_admin(request)

    vault = get_object_or_404(Vault, pk=vault_id)
    credencial = get_object_or_404(Credencial, pk=pk, vault=vault)
    secreto = ""

    if request.method == "POST":
        acceso_codigo = request.POST.get("acceso_codigo", "")
        if vault.check_access_code(acceso_codigo):
            secreto = credencial.get_secret()
            _log_action(vault, request.user, "secreto_visto", credencial=credencial)
        else:
            messages.error(request, "Codigo de acceso invalido.")

    return render(request, "passwords/credencial_secret.html", {
        "vault": vault,
        "credencial": credencial,
        "secreto": secreto,
        "requiere_codigo": vault.acceso_requerido,
    })


@login_required
def credenciales_export(request, vault_id):
    _require_admin(request)

    vault = get_object_or_404(Vault, pk=vault_id)
    credenciales = Credencial.objects.filter(vault=vault).order_by("-fecha_creacion")

    wb = Workbook()
    ws = wb.active
    ws.title = "Credenciales"
    ws.append(["Titulo", "Usuario", "URL", "Estado", "Expiracion", "Creado", "Actualizado"])

    for cred in credenciales:
        ws.append([
            cred.titulo,
            cred.usuario,
            cred.url,
            cred.get_estado_display(),
            cred.fecha_expiracion.strftime("%Y-%m-%d") if cred.fecha_expiracion else "",
            cred.fecha_creacion.strftime("%Y-%m-%d"),
            cred.fecha_actualizacion.strftime("%Y-%m-%d"),
        ])

    _log_action(vault, request.user, "export_excel")

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f"attachment; filename=credenciales_{vault.id}.xlsx"
    wb.save(response)
    return response


@login_required
def logs(request, vault_id):
    _require_admin(request)

    vault = get_object_or_404(Vault, pk=vault_id)
    qs = AccesoLog.objects.filter(vault=vault).select_related("credencial", "usuario")

    accion = request.GET.get("accion", "").strip()
    q = request.GET.get("q", "").strip()
    if accion:
        qs = qs.filter(accion=accion)
    if q:
        qs = qs.filter(
            Q(credencial__titulo__icontains=q)
            | Q(usuario__username__icontains=q)
            | Q(detalle__icontains=q)
        )

    acciones = (
        AccesoLog.objects.filter(vault=vault)
        .values_list("accion", flat=True)
        .distinct()
        .order_by("accion")
    )

    return render(request, "passwords/logs_list.html", {
        "vault": vault,
        "logs": qs,
        "acciones": acciones,
        "filtro_accion": accion,
        "filtro_q": q,
    })
