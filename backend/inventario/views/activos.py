"""Activos: lista, detalle, software, alta, edición y baja."""


import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render



from ..forms import (
    ActivoForm,
)
from ..models import (
    Activo, SoftwareInstalado,
)

from ..software_sync import refrescar_activo, software_guardado, ultimo_reporte
from accounts.permisos import requiere_permiso

logger = logging.getLogger(__name__)



# ── Lista ──────────────────────────────────────────────────────────────────────

@requiere_permiso("inventario", "lectura")
def lista_activos(request):
    qs = Activo.objects.select_related("catalogo")

    tipo = request.GET.get("tipo", "")
    estado = request.GET.get("estado", "")
    q = request.GET.get("q", "").strip()

    if tipo:
        qs = qs.filter(tipo_dispositivo=tipo)
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(
            Q(serial__icontains=q)
            | Q(marca__icontains=q)
            | Q(modelo__icontains=q)
            | Q(imei__icontains=q)
        )

    from .models import ESTADOS, TIPOS
    stats = Activo.objects.aggregate(
        total=Count("pk"),
        asignados=Count(Case(When(estado="asignado", then=Value(1)), output_field=IntegerField())),
        disponibles=Count(Case(When(estado="disponible", then=Value(1)), output_field=IntegerField())),
        baja=Count(Case(When(estado="dado_de_baja", then=Value(1)), output_field=IntegerField())),
    )

    page_number = request.GET.get("page", "1")
    paginator = Paginator(qs.order_by("marca", "modelo", "serial"), 20)
    page_obj = paginator.get_page(page_number)

    ctx = {
        "activos": page_obj.object_list,
        "page_obj": page_obj,
        "tipos": TIPOS,
        "estados": ESTADOS,
        "filtro_tipo": tipo,
        "filtro_estado": estado,
        "filtro_q": q,
        "stats": stats,
    }

    if request.headers.get("HX-Request"):
        return render(request, "inventario/partials/tabla.html", ctx)

    return render(request, "inventario/lista.html", ctx)


# ── Detalle ────────────────────────────────────────────────────────────────────

@requiere_permiso("inventario", "lectura")
def detalle_activo(request, pk):
    activo = get_object_or_404(
        Activo.objects.select_related("catalogo").prefetch_related(
            "asignaciones__usuario", "asignaciones__acta"
        ),
        pk=pk,
    )
    asignacion_activa = None
    actas = []
    for a in activo.asignaciones.all():
        if a.activa and asignacion_activa is None:
            asignacion_activa = a
        if hasattr(a, "acta"):
            actas.append(a.acta)

    movimientos = activo.movimientos.select_related("usuario_destino").order_by("-fecha", "-fecha_creacion")

    ctx = {
        "activo": activo,
        "asignacion_activa": asignacion_activa,
        "movimientos": movimientos,
        "actas": actas,
    }
    return render(request, "inventario/detalle.html", ctx)


# ── Software instalado (inventario de aplicaciones) ───────────────────────────

@requiere_permiso("inventario", "lectura")
def software_activo(request, pk):
    """Listado del software instalado que se conoce de este activo.

    Se lee de la base, no de OCS: la tabla se llena al sincronizar y guarda el
    histórico, así que la página no depende de que OCS esté respondiendo y se
    pueden cruzar los datos entre equipos. `?actualizar=1` (o el botón) fuerza
    una lectura de OCS y escribe solo las diferencias.

    El filtro es sobre la lista ya traída y no sobre SQL a propósito: son ~100
    filas por equipo, y filtrar en la base obligaría a perder el histórico de
    lo que dejó de estar instalado.
    """
    activo = get_object_or_404(Activo, pk=pk)
    equipo = activo.equipo_ocs.first() if hasattr(activo, "equipo_ocs") else None
    resumen = None
    estado = "ok" if equipo else "sin_equipo"
    detalle = ""

    if request.GET.get("actualizar"):
        info = refrescar_activo(activo)
        estado, detalle, resumen = info["estado"], info["detalle"], info["resumen"]
        if resumen:
            cambios = resumen["nuevos"] + resumen["actualizados"] + resumen[
                "desinstalados"
            ] + resumen["reinstalados"] + resumen["coexistencia"]
            if cambios:
                messages.success(
                    request, f"Inventario actualizado: {cambios} cambios guardados en la base."
                )
            else:
                messages.info(request, "Inventario actualizado: no hubo cambios en OCS.")
    elif not equipo:
        detalle = (
            "Este activo no está vinculado a ningún equipo de OCS, "
            "así que no hay inventario de software para él."
        )

    filas = list(software_guardado(activo))
    total_guardado = len(filas)

    q = request.GET.get("q", "").strip()
    if q:
        ql = q.lower()
        filas = [
            f
            for f in filas
            if ql in f.nombre.lower()
            or ql in f.version.lower()
            or ql in f.fabricante.lower()
        ]

    ctx = {
        "activo": activo,
        "software": filas,
        "total": len(filas),
        "total_guardado": total_guardado,
        "oculto": total_guardado - len(filas),
        "estado": estado,
        "detalle": detalle,
        "filtro_q": q,
        "resumen": resumen,
        "ultima_sync": ultimo_reporte(activo),
    }
    return render(request, "inventario/software.html", ctx)


#: Nombres que OCS reporta para componentes de Windows, actualizaciones y
#: antivirus. En un equipo real son más de la mitad de las entradas y tapan
#: los programas que la gente usa de verdad, pero no se ocultan por defecto:
#: el listado completo es el dato, y esconder entradas "por comodidad" hizo
#: que otros listados parecieran incompletos sin explicación.


# ── Consulta cruzada de software ───────────────────────────────────────────────

@requiere_permiso("inventario", "lectura")
def software_global(request):
    """Qué programas hay y en cuántos equipos está cada uno.

    Es la razón de guardar el software en la base: sin histórico, "quién tiene
    Office" o "en cuál falta el antivirus" no se pueden contestar.
    """
    q = request.GET.get("q", "").strip()
    consulta = SoftwareInstalado.objects.filter(presente=True)
    if q:
        consulta = consulta.filter(
            Q(nombre__icontains=q)
            | Q(fabricante__icontains=q)
            | Q(version__icontains=q)
        )

    # Un programa puede estar en dos versiones en el mismo equipo (runtimes de
    # 32 y 64 bits), así que se cuenta sobre (nombre, activo) distintos.
    programas = (
        consulta.values("nombre")
        .annotate(equipos=Count("activo", distinct=True))
        .order_by("-equipos", "nombre")
    )

    ctx = {
        "programas": list(programas[:200]),
        "filtro_q": q,
        "total_activos": Activo.objects.exclude(estado="dado_de_baja").count(),
    }
    return render(request, "inventario/software_global.html", ctx)


# ── Crear ──────────────────────────────────────────────────────────────────────

@requiere_permiso("inventario", "escritura")
def crear_activo(request):
    if request.method == "POST":
        form = ActivoForm(request.POST, request.FILES)
        if form.is_valid():
            activo = form.save()
            messages.success(request, f"Activo «{activo}» creado correctamente.")
            return redirect("inventario:detalle", pk=activo.pk)
        else:
            messages.error(request, "Corrige los errores del formulario.")
    else:
        form = ActivoForm()

    return render(request, "inventario/form.html", {"form": form, "titulo": "Nuevo Activo"})


# ── Editar ─────────────────────────────────────────────────────────────────────

@requiere_permiso("inventario", "escritura")
def editar_activo(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    if request.method == "POST":
        form = ActivoForm(request.POST, request.FILES, instance=activo)
        if form.is_valid():
            form.save()
            messages.success(request, f"Activo «{activo}» actualizado.")
            return redirect("inventario:detalle", pk=activo.pk)
        else:
            messages.error(request, "Corrige los errores del formulario.")
    else:
        form = ActivoForm(instance=activo)

    return render(request, "inventario/form.html", {"form": form, "titulo": "Editar Activo", "activo": activo})


# ── Baja (toggle) ──────────────────────────────────────────────────────────────

@requiere_permiso("inventario", "escritura")
def toggle_baja_activo(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    if request.method == "POST":
        if activo.estado == "dado_de_baja":
            activo.estado = "disponible"
            messages.warning(request, f"Activo «{activo}» reactivado.")
        else:
            if activo.asignaciones.filter(activa=True).exists():
                messages.error(request, "No se puede dar de baja un activo asignado. Devuélvelo primero.")
                return redirect("inventario:detalle", pk=activo.pk)
            activo.estado = "dado_de_baja"
            messages.success(request, f"Activo «{activo}» dado de baja.")
        activo.save()
    return redirect("inventario:detalle", pk=activo.pk)
