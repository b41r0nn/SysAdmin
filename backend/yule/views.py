import logging

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .client import build_client
from .forms import ConfiguracionYuleForm, VincularActivoForm
from .models import EquipoOCS, SincronizacionLog, ConfiguracionYule
from .sync import sincronizar_equipos_ocs, verificar_equipos_sin_match, buscar_posibles_matches
from accounts.permisos import requiere_permiso

logger = logging.getLogger(__name__)


def _mask_token(value: str) -> str:
    """Enmascara token OCS para mostrar en UI"""
    if not value:
        return ""
    if len(value) <= 10:
        return "*" * len(value)
    return f"{value[:2]}***{value[-4:]}"


@requiere_permiso("inventario", "lectura")
def index(request):
    """Vista principal de Yule - Status de configuración"""
    client = build_client()
    config = ConfiguracionYule.objects.filter(activa=True).order_by("id").first()
    
    # Estadísticas
    total_equipos = EquipoOCS.objects.count()
    equipos_vinculados = EquipoOCS.objects.filter(activo_local__isnull=False).count()
    equipos_sin_match = EquipoOCS.objects.filter(activo_local__isnull=True).count()
    
    # Últimas sincronizaciones
    ultimas_syncs = SincronizacionLog.objects.all()[:5]
    
    # Test de conexión (solo si la integración está activa y configurada)
    conexion_ok = False
    error_conexion = ""
    if client.is_configured():
        conexion_ok = client.test_connection()
        if not conexion_ok:
            error_conexion = "No se puede conectar a OCS. Verificar credenciales."
    
    # Datos de conexión: prioridad BD, fallback settings (despliegue actual)
    if config and config.url and config.usuario:
        ocs_base_url = config.url
        ocs_user = config.usuario
        ocs_token = _mask_token(config.get_ocs_password())
    else:
        ocs_base_url = settings.OCS_BASE_URL
        ocs_user = settings.OCS_USER
        ocs_token = _mask_token(settings.OCS_TOKEN)
    
    integracion_activa = config.integracion_activa if config else bool(ocs_base_url and ocs_user)
    
    context = {
        "ocs_base_url": ocs_base_url,
        "ocs_user": ocs_user,
        "ocs_token": ocs_token,
        "ocs_verify_ssl": settings.OCS_VERIFY_SSL,
        "ocs_configured": client.is_configured(),
        "integracion_activa": integracion_activa,
        "conexion_ok": conexion_ok,
        "error_conexion": error_conexion,
        "config": config,
        "total_equipos": total_equipos,
        "equipos_vinculados": equipos_vinculados,
        "equipos_sin_match": equipos_sin_match,
        "ultimas_syncs": ultimas_syncs,
    }
    return render(request, "yule/index.html", context)


@requiere_permiso("inventario", "escritura")
def configuracion(request):
    """Editar la configuración OCS (url/usuario/contraseña/activa/sync)."""
    config = ConfiguracionYule.objects.filter(activa=True).order_by("id").first()
    
    if request.method == "POST":
        if config is None:
            config = ConfiguracionYule(nombre="Configuración OCS", activa=True)
        form = ConfiguracionYuleForm(request.POST, instance=config)
        if form.is_valid():
            instancia = form.save(commit=False)
            if instancia.creada_por is None:
                instancia.creada_por = request.user
            instancia.save()
            messages.success(request, "Configuración OCS guardada correctamente.")
            return redirect("yule:index")
    else:
        form = ConfiguracionYuleForm(instance=config)
    
    return render(request, "yule/configuracion_form.html", {
        "form": form,
        "config": config,
        "titulo": "Configuración OCS",
    })


@requiere_permiso("inventario", "lectura")
def equipos_lista(request):
    """Lista de todos los equipos OCS sincronizados"""
    equipos = EquipoOCS.objects.all()
    
    # Filtros
    filtro = request.GET.get("filtro", "todos")
    if filtro == "vinculados":
        equipos = equipos.filter(activo_local__isnull=False)
    elif filtro == "sin_match":
        equipos = equipos.filter(activo_local__isnull=True)
    elif filtro == "sin_reporte":
        equipos = equipos.filter(visto_en_ultima_sync=False)
    
    # Búsqueda
    q = request.GET.get("q", "").strip()
    if q:
        equipos = equipos.filter(
            Q(nombre_host__icontains=q) |
            Q(mac_address__icontains=q) |
            Q(id_ocs__icontains=q) |
            Q(usuario_dominio__icontains=q)
        )
    
    # Paginación simple
    pagina = request.GET.get("page", 1)
    items_por_pagina = 25
    try:
        pagina = int(pagina)
    except (ValueError, TypeError):
        pagina = 1
    
    start_idx = (pagina - 1) * items_por_pagina
    end_idx = start_idx + items_por_pagina
    
    total_items = equipos.count()
    equipos_paginados = equipos[start_idx:end_idx]
    
    total_paginas = (total_items + items_por_pagina - 1) // items_por_pagina
    
    context = {
        "equipos": equipos_paginados,
        "filtro": filtro,
        "q": q,
        "pagina_actual": pagina,
        "total_paginas": total_paginas,
        "total_items": total_items,
        "tiene_pagina_anterior": pagina > 1,
        "tiene_pagina_siguiente": pagina < total_paginas,
    }
    
    return render(request, "yule/equipos_lista.html", context)


@requiere_permiso("inventario", "lectura")
def equipo_detalle(request, pk):
    """Detalle de un equipo OCS"""
    equipo = get_object_or_404(EquipoOCS, pk=pk)

    # Candidatos en el inventario, con el motivo de cada coincidencia
    posibles_matches = buscar_posibles_matches(equipo)

    # Información de sincronización
    primera_sync = SincronizacionLog.objects.filter(
        equipos_nuevos__gt=0
    ).order_by("fecha_inicio").first()

    context = {
        "equipo": equipo,
        "posibles_matches": posibles_matches,
        "form_vincular": VincularActivoForm(equipo=equipo),
        "dias_sin_reporte": equipo.dias_sin_reporte,
        "primera_sync": primera_sync,
    }

    return render(request, "yule/equipo_detalle.html", context)


@requiere_permiso("inventario", "escritura")
@require_POST
def vincular_activo(request, pk):
    """Vincula un equipo de OCS con un activo del inventario local.

    Hasta ahora esto solo se podía hacer editando el equipo a mano en el admin de
    Django: la pantalla de "sin match" llevaba al alta de activos y el detalle
    mostraba candidatos que no eran accionables. El resultado era que el equipo
    quedaba huérfano aunque el activo existiera.
    """
    equipo = get_object_or_404(EquipoOCS, pk=pk)

    if equipo.esta_vinculado:
        messages.error(
            request,
            f"{equipo.nombre_host} ya está vinculado a "
            f"{equipo.activo_local.serial}. Desvincúlalo primero si vas a cambiarlo.",
        )
        return redirect("yule:equipo_detalle", pk=equipo.pk)

    form = VincularActivoForm(request.POST, equipo=equipo)
    if form.is_valid():
        activo = form.cleaned_data["activo"]
        equipo.activo_local = activo
        equipo.save(update_fields=["activo_local"])
        logger.info(
            "Equipo OCS %s vinculado al activo %s por %s",
            equipo.id_ocs, activo.serial, request.user.username,
        )
        messages.success(
            request,
            f"{equipo.nombre_host} vinculado a {activo.serial}. "
            f"El software de OCS ya aparece en su hoja de vida.",
        )
    else:
        messages.error(request, " ".join(form.errors.get("__all__", [])) or "No se pudo vincular.")

    return redirect("yule:equipo_detalle", pk=equipo.pk)


@requiere_permiso("inventario", "escritura")
@require_POST
def desvincular_activo(request, pk):
    """Quita el vínculo entre un equipo de OCS y su activo."""
    equipo = get_object_or_404(EquipoOCS, pk=pk)

    if not equipo.esta_vinculado:
        messages.warning(request, f"{equipo.nombre_host} no estaba vinculado a ningún activo.")
    else:
        serial = equipo.activo_local.serial
        equipo.activo_local = None
        equipo.save(update_fields=["activo_local"])
        logger.info(
            "Equipo OCS %s desvinculado del activo %s por %s",
            equipo.id_ocs, serial, request.user.username,
        )
        messages.warning(
            request,
            f"{equipo.nombre_host} quedó desvinculado de {serial}. "
            f"Vuelve a aparecer en la lista de equipos sin match.",
        )

    return redirect("yule:equipo_detalle", pk=equipo.pk)


@requiere_permiso("inventario", "lectura")
def api_buscar_activos(request):
    """Autocompletado de activos para el selector de vinculación.

    Devuelve JSON con los primeros 20 activos que coincidan con `q` en serial,
    numero interno, nombre de equipo o marca/modelo. Los equipos OCS ya
    vinculados a otro activo vienen marcados para que el selector los pueda
    descartar en cliente.
    """
    from inventario.models import Activo

    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"resultados": []})

    consulta = (
        Q(serial__icontains=q)
        | Q(nombre_equipo__icontains=q)
        | Q(marca__icontains=q)
        | Q(modelo__icontains=q)
    )
    # numero_interno es un entero: usarlo en la consulta con texto lanza un
    # ValueError y el buscador devuelve un 500 en vez de "sin resultados".
    if q.isdigit():
        consulta |= Q(numero_interno=q)

    activos = Activo.objects.filter(consulta).order_by("numero_interno", "serial")[:20]

    resultados = [
        {
            "id": a.pk,
            "serial": a.serial,
            "nombre_equipo": a.nombre_equipo,
            "marca": a.marca,
            "modelo": a.modelo,
            "numero_interno": a.numero_interno,
            "ocupado": a.equipo_ocs.exists(),
        }
        for a in activos
    ]
    return JsonResponse({"resultados": resultados})


@requiere_permiso("inventario", "escritura")
@require_POST
def sincronizar(request):
    
    logger.info(f"Sincronización iniciada por {request.user.username}")
    
    log, mensaje = sincronizar_equipos_ocs(usuario=request.user, force=True)
    
    if log.fue_exitosa:
        messages.success(request, mensaje)
    else:
        messages.error(request, mensaje)
    
    return redirect("yule:index")


@requiere_permiso("inventario", "lectura")
def historial_sincronizaciones(request):
    """Historial de sincronizaciones"""
    logs = SincronizacionLog.objects.all()
    
    # Filtros
    estado = request.GET.get("estado", "")
    if estado:
        logs = logs.filter(estado=estado)
    
    context = {
        "logs": logs[:100],  # Últimas 100
        "estado_filtro": estado,
    }
    
    return render(request, "yule/historial_sincronizaciones.html", context)


@requiere_permiso("inventario", "lectura")
def equipos_sin_match(request):
    """Vista especial para equipos sin vincular a activos"""
    equipos = verificar_equipos_sin_match()

    # Candidatos por equipo, para poder ofrecer la vinculación sin salir de la
    # lista. Se entrega como lista de tuplas porque una plantilla no puede indexar
    # un dict con una clave variable.
    matches_por_equipo = [(e, buscar_posibles_matches(e)) for e in equipos]

    context = {
        "equipos": equipos,
        "total": equipos.count(),
        "matches_por_equipo": matches_por_equipo,
        "form_vincular": VincularActivoForm(),
    }

    return render(request, "yule/equipos_sin_match.html", context)


@requiere_permiso("inventario", "lectura")
def test_conexion_ocs(request):
    """API para testear conexión OCS"""
    client = build_client()
    
    if not client.is_configured():
        return JsonResponse({
            "success": False,
            "error": "OCS no configurado",
        })
    
    try:
        if client.test_connection():
            return JsonResponse({
                "success": True,
                "mensaje": "Conexión exitosa con OCS",
            })
        else:
            return JsonResponse({
                "success": False,
                "error": "No se puede conectar a OCS",
            })
    except Exception as e:
        logger.error(f"Error en test de conexión: {e}")
        return JsonResponse({
            "success": False,
            "error": str(e),
        })
