"""
Servicio de sincronización entre OCS e Inventario local.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from django.utils import timezone

from .client import build_client, OCSClientException
from .models import EquipoOCS, SincronizacionLog, ConfiguracionYule

logger = logging.getLogger(__name__)


def _extract_equipo_data(ocs_computer: Dict) -> Dict:
    """Extrae datos relevantes de respuesta OCS"""
    # OCS puede variar en estructura según versión
    # Este mapeo es genérico y requiere ajustes según tu OCS
    
    hardware = ocs_computer.get("hardware", {})
    if isinstance(hardware, list):
        hardware = hardware[0] if hardware else {}
    
    bios = ocs_computer.get("bios", {})
    if isinstance(bios, list):
        bios = bios[0] if bios else {}
    
    networks = ocs_computer.get("networks", [])
    if not isinstance(networks, list):
        networks = []
    
    # Obtener primer MAC y IP
    mac_address = ""
    ip_address = ""
    if networks:
        net = networks[0] if isinstance(networks[0], dict) else {}
        mac_address = net.get("macaddr", "")
        ip_address = net.get("ipaddress", "")

    return {
        "id_ocs": str(ocs_computer.get("id", "")),
        "nombre_host": ocs_computer.get("name", "Unknown"),
        "usuario_dominio": ocs_computer.get("user", ""),
        "so_nombre": hardware.get("osname", ""),
        "so_version": hardware.get("osversion", ""),
        "procesador": hardware.get("processors", [{}])[0].get("name", "") if hardware.get("processors") else "",
        "memoria_ram_mb": int(hardware.get("memory", 0)) if hardware.get("memory") else None,
        "almacenamiento_total_gb": None,  # OCS no siempre proporciona esto
        "serial_bios": bios.get("sn", ""),
        "mac_address": mac_address,
        "ip_address": ip_address,
        "ultimo_reporte_ocs": datetime.now(timezone.utc),
    }


def sincronizar_equipos_ocs(usuario=None, force: bool = False) -> Tuple[SincronizacionLog, str]:
    """
    Sincroniza equipos desde OCS con BD local.
    
    Args:
        usuario: Usuario que realiza la sincronización
        force: Fuerza sincronización aunque no haya pasado frecuencia
        
    Returns:
        Tupla (SincronizacionLog, mensaje_resumido)
    """
    fecha_inicio = timezone.now()
    
    log = SincronizacionLog(
        realizado_por=usuario,
        estado="exitosa",
    )
    
    try:
        # Verificar frecuencia de sincronización
        config = ConfiguracionYule.objects.filter(activa=True).first()
        if not force and config:
            if config.ultima_sincronizacion:
                tiempo_desde_ultima = timezone.now() - config.ultima_sincronizacion
                frecuencia = timedelta(minutes=config.frecuencia_sync_minutos)
                if tiempo_desde_ultima < frecuencia:
                    msg = f"Sincronización muy reciente. Próxima en {(frecuencia - tiempo_desde_ultima).total_seconds() / 60:.0f} min"
                    log.estado = "parcial"
                    log.mensaje_error = msg
                    log.save()
                    return log, msg
        
        # Obtener equipos de OCS. Si la integración está desactivada o el
        # cliente no está configurado, no corre (degradación graciosa: log
        # parcial, sin error).
        client = build_client()
        
        if not client.is_configured():
            msg = "Integración OCS desactivada o sin configurar. No se sincronizó."
            logger.info(msg)
            log.estado = "parcial"
            log.mensaje_error = msg
            log.fecha_fin = timezone.now()
            log.duracion_segundos = int((log.fecha_fin - fecha_inicio).total_seconds())
            log.save()
            return log, msg
        
        logger.info("Iniciando sincronización con OCS...")
        equipos_ocs = client.get_computers()
        
        if not equipos_ocs:
            logger.warning("OCS retornó lista vacía de equipos")
            equipos_ocs = []
        
        logger.info(f"OCS retornó {len(equipos_ocs)} equipos")
        
        # Marcar todos como no vistos inicialmente
        EquipoOCS.objects.all().update(visto_en_ultima_sync=False)
        
        equipos_nuevos = 0
        equipos_actualizados = 0
        
        # Procesar cada equipo de OCS
        for equipo_data in equipos_ocs:
            try:
                datos_limpios = _extract_equipo_data(equipo_data)
                id_ocs = datos_limpios["id_ocs"]
                
                # Buscar o crear equipo
                equipo, creado = EquipoOCS.objects.update_or_create(
                    id_ocs=id_ocs,
                    defaults={
                        **datos_limpios,
                        "visto_en_ultima_sync": True,
                    }
                )
                
                if creado:
                    equipos_nuevos += 1
                    logger.info(f"Nuevo equipo detectado: {equipo.nombre_host} ({id_ocs})")
                else:
                    equipos_actualizados += 1
                    logger.debug(f"Equipo actualizado: {equipo.nombre_host}")
                    
            except Exception as e:
                logger.error(f"Error procesando equipo OCS: {str(e)}", exc_info=True)
                continue
        
        # Equipos que desaparecieron
        equipos_desaparecidos = EquipoOCS.objects.filter(
            visto_en_ultima_sync=False
        ).count()
        
        # Actualizar log
        log.equipos_detectados = len(equipos_ocs)
        log.equipos_nuevos = equipos_nuevos
        log.equipos_actualizados = equipos_actualizados
        log.equipos_desaparecidos = equipos_desaparecidos
        
        # Actualizar configuración
        if config:
            config.ultima_sincronizacion = fecha_inicio
            config.save()
        
        fecha_fin = timezone.now()
        log.fecha_fin = fecha_fin
        log.duracion_segundos = int((fecha_fin - fecha_inicio).total_seconds())
        log.save()
        
        mensaje = (
            f"Sincronización exitosa: "
            f"{len(equipos_ocs)} detectados, "
            f"{equipos_nuevos} nuevos, "
            f"{equipos_actualizados} actualizados, "
            f"{equipos_desaparecidos} desaparecidos"
        )
        
        logger.info(mensaje)
        return log, mensaje
        
    except OCSClientException as e:
        logger.error(f"Error de conexión OCS: {str(e)}")
        log.estado = "fallo"
        log.mensaje_error = f"Error OCS: {str(e)}"
        log.fecha_fin = timezone.now()
        log.duracion_segundos = int((log.fecha_fin - fecha_inicio).total_seconds())
        log.save()
        return log, f"Fallo en sincronización: {str(e)}"
        
    except Exception as e:
        logger.error(f"Error inesperado en sincronización: {str(e)}", exc_info=True)
        log.estado = "fallo"
        log.mensaje_error = f"Error inesperado: {str(e)}"
        log.fecha_fin = timezone.now()
        log.duracion_segundos = int((log.fecha_fin - fecha_inicio).total_seconds())
        log.save()
        return log, f"Error: {str(e)}"


def verificar_equipos_sin_match() -> List[EquipoOCS]:
    """Retorna equipos OCS sin vincular a activos locales"""
    return EquipoOCS.objects.filter(activo_local__isnull=True).order_by("-ultimo_reporte_ocs")


def buscar_posibles_matches(equipo: EquipoOCS, por_serial: bool = True, 
                           por_mac: bool = True, por_hostname: bool = False) -> List:
    """
    Busca posibles coincidencias en inventario local.
    
    Args:
        equipo: EquipoOCS a buscar
        por_serial: Buscar por serial BIOS
        por_mac: Buscar por MAC address
        por_hostname: Buscar por hostname (menos confiable)
        
    Returns:
        Lista de activos potencialmente coincidentes
    """
    from inventario.models import Activo
    
    matches = []
    
    # Buscar por serial
    if por_serial and equipo.serial_bios:
        matches.extend(
            Activo.objects.filter(serial__icontains=equipo.serial_bios)
        )
    
    # Buscar por MAC
    if por_mac and equipo.mac_address:
        matches.extend(
            Activo.objects.filter(mac_equipo__icontains=equipo.mac_address)
        )
    
    # Búsqueda por hostname (muy imprecisa, opcional)
    if por_hostname and equipo.nombre_host:
        matches.extend(
            Activo.objects.filter(observaciones__icontains=equipo.nombre_host)
        )
    
    # Remover duplicados manteniendo orden
    seen = set()
    unique_matches = []
    for m in matches:
        if m.id not in seen:
            seen.add(m.id)
            unique_matches.append(m)
    
    return unique_matches
