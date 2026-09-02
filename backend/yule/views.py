import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .client import build_client
from .models import EquipoOCS, SincronizacionLog, ConfiguracionYule
from .sync import sincronizar_equipos_ocs, verificar_equipos_sin_match, buscar_posibles_matches

logger = logging.getLogger(__name__)


def _mask_token(value: str) -> str:
    """Enmascara token OCS para mostrar en UI"""
    if not value:
        return ""
    if len(value) <= 10:
        return "*" * len(value)
    return f"{value[:2]}***{value[-4:]}"


@login_required
def index(request):
    """Vista principal de Yule - Status de configuración"""
    client = build_client()
    config = ConfiguracionYule.objects.filter(activa=True).first()
    
    # Estadísticas
    total_equipos = EquipoOCS.objects.count()
    equipos_vinculados = EquipoOCS.objects.filter(activo_local__isnull=False).count()
    equipos_sin_match = EquipoOCS.objects.filter(activo_local__isnull=True).count()
    
    # Últimas sincronizaciones
    ultimas_syncs = SincronizacionLog.objects.all()[:5]
    
    # Test de conexión
    conexion_ok = False
    error_conexion = ""
    if client.is_configured():
        conexion_ok = client.test_connection()
        if not conexion_ok:
            error_conexion = "No se puede conectar a OCS. Verificar credenciales."
    
    context = {
        "ocs_base_url": settings.OCS_BASE_URL,
        "ocs_user": settings.OCS_USER,
        "ocs_token": _mask_token(settings.OCS_TOKEN),
        "ocs_verify_ssl": settings.OCS_VERIFY_SSL,
        "ocs_configured": client.is_configured(),
        "conexion_ok": conexion_ok,
        "error_conexion": error_conexion,
        "config": config,
        "total_equipos": total_equipos,
        "equipos_vinculados": equipos_vinculados,
        "equipos_sin_match": equipos_sin_match,
        "ultimas_syncs": ultimas_syncs,
    }
    return render(request, "yule/index.html", context)


@login_required
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


@login_required
def equipo_detalle(request, pk):
    """Detalle de un equipo OCS"""
    equipo = get_object_or_404(EquipoOCS, pk=pk)
    
    # Posibles matches en inventario
    posibles_matches = buscar_posibles_matches(
        equipo,
        por_serial=True,
        por_mac=True,
        por_hostname=False,
    )
    
    # Información de sincronización
    primera_sync = SincronizacionLog.objects.filter(
        equipos_nuevos__gt=0
    ).order_by("fecha_inicio").first()
    
    context = {
        "equipo": equipo,
        "posibles_matches": posibles_matches,
        "dias_sin_reporte": equipo.dias_sin_reporte,
        "primera_sync": primera_sync,
    }
    
    return render(request, "yule/equipo_detalle.html", context)


@login_required
@require_POST
def sincronizar(request):
    """Inicia sincronización manual con OCS"""
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Solo administradores pueden sincronizar")
        return redirect("yule:index")
    
    logger.info(f"Sincronización iniciada por {request.user.username}")
    
    log, mensaje = sincronizar_equipos_ocs(usuario=request.user, force=True)
    
    if log.fue_exitosa:
        messages.success(request, mensaje)
    else:
        messages.error(request, mensaje)
    
    return redirect("yule:index")


@login_required
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


@login_required
def equipos_sin_match(request):
    """Vista especial para equipos sin vincular a activos"""
    equipos = verificar_equipos_sin_match()
    
    context = {
        "equipos": equipos,
        "total": equipos.count(),
    }
    
    return render(request, "yule/equipos_sin_match.html", context)


@login_required
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
