from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render

from accounts.permisos import requiere_permiso

from .forms import ConfiguracionForm
from .models import ConfiguracionSistema, RegistroAuditoria


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