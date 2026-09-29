"""Sincroniza los equipos de Yule con OCS."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .client import build_client, OCSClientException
from .models import EquipoOCS, SincronizacionLog, ConfiguracionYule

logger = logging.getLogger(__name__)


def _get_ci(data: Any, *keys: str, default: Any = "") -> Any:
    """Busca una clave sin distinguir mayúsculas.

    La API de OCS devuelve los nombres de columna de la tabla `hardware` tal
    cual están en la BD (mayúsculas: `NAME`, `OSNAME`, `LASTCOME`), mientras que
    otras instalaciones los devuelven en minúsculas. Leer solo en minúsculas
    dejaba todos los campos vacíos y el equipo aparecía como "Unknown".
    """
    if not isinstance(data, dict):
        return default
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    lowered = {str(k).lower(): v for k, v in data.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return default


def _section(data: Any, *keys: str) -> Dict[str, Any]:
    """Devuelve una sección de la respuesta (hardware, bios) como dict plano.

    OCS 2.12 devuelve cada sección de tres formas distintas según la tabla:
    envuelta en el ID del equipo (`{"1": {...}}`), como lista de filas
    (`bios: [{"SSN": "..."}]`) o como dict plano. Se normaliza todo a dict.
    """
    value = _get_ci(data, *keys, default={})
    if isinstance(value, list):
        # Secciones 1-a-N (bios, storages, memories...) o N-a-1 indexada por ID.
        if value and isinstance(value[0], dict):
            value = value[0]
        else:
            indexed = [v for v in value if isinstance(v, dict)]
            value = indexed[0] if len(indexed) == 1 else {}
    if not isinstance(value, dict):
        return {}
    if len(value) == 1:
        inner = next(iter(value.values()))
        if isinstance(inner, dict):
            return inner
    return value


def _parse_ocs_datetime(value: Any) -> Optional[datetime]:
    """Parsea la fecha de último reporte de OCS (`LASTCOME`).

    OCS la escribe con `NOW()` evaluado por el servidor de BD, que corre en UTC,
    así que llega como hora naive pero en UTC. En el server el access log
    marcaba `22:27:57 +0200` y `LASTCOME` traía `20:27:57`: el mismo instante.
    Interpretarlo como hora local (America/Bogota) corría el reporte 5 horas.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        parsed = parse_datetime(text)
        if parsed is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if parsed is None:
            logger.warning(f"No se pudo interpretar la fecha de OCS: {text!r}")
            return None
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _lista(data: Any, *keys: str) -> List[Any]:
    """Normaliza una sección repetible (networks, storages, cpus) a lista de dicts."""
    value = _get_ci(data, *keys, default=[])
    if isinstance(value, dict):
        return [v for v in value.values() if isinstance(v, dict)]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def _red_principal(hardware: Dict[str, Any], networks: List[Dict]) -> Tuple[str, str]:
    """Devuelve (mac, ip) de la interfaz física del equipo.

    `hardware.IPADDR` ya trae la IP real del agente, así que se busca la
    interfaz que la tenga y se usa su MAC. Sin ese cruce se tomaba la primera
    interfaz: el equipo tenía 48 y la primera es la virtual del firewall
    (`00:09:0F:AA:00:01`), inservible para cruzar contra el inventario local.

    Orden: 1) la interfaz con la IP de `hardware`, 2) la primera activa
    (`STATUS` = Up), 3) la primera con MAC no nula. La IP se resuelve por
    separado porque la interfaz de management suele tener MAC pero no IP.
    """
    ip_hardware = _get_ci(hardware, "ipaddr", "ipsrc")

    mac_activa = ""
    mac_cualquiera = ""
    for net in networks:
        net_ip = _get_ci(net, "ipaddress", "ip")
        net_mac = _get_ci(net, "macaddr", "macaddress")
        if not net_mac or net_mac == "00:00:00:00:00:00":
            continue
        if ip_hardware and net_ip == ip_hardware:
            return net_mac, net_ip
        if not mac_cualquiera:
            mac_cualquiera = net_mac
        if not mac_activa and _get_ci(net, "status", default="").lower() == "up":
            mac_activa = net_mac

    mac = mac_activa or mac_cualquiera

    ip = ip_hardware
    if not ip:
        for net in networks:
            net_ip = _get_ci(net, "ipaddress", "ip")
            if net_ip:
                ip = net_ip
                break

    return mac, ip


def _procesador(hardware: Dict[str, Any], computer: Dict[str, Any]) -> str:
    """Nombre del CPU.

    En OCS 2.12 `hardware.PROCESSORS` es la frecuencia en MHz (entero 1300), no
    una lista de CPUs, por eso salía vacío. El nombre real está en
    `hardware.PROCESSORT` y, como respaldo, en la primera fila de `cpus`.
    """
    processor_name = _get_ci(hardware, "processort", "processorname")
    if processor_name and not isinstance(processor_name, (int, float)):
        return str(processor_name)

    for source in (_get_ci(computer, "cpus", default=[]), _get_ci(hardware, "processors", default=[])):
        # `cpus` es lista de filas; `processors` puede ser dict de campos de un
        # solo CPU, así que ambas formas se normalizan a filas.
        if isinstance(source, dict):
            rows = [source]
        elif isinstance(source, list):
            rows = [row for row in source if isinstance(row, dict)]
        else:
            continue
        for row in rows:
            name = _get_ci(row, "type", "name", "caption", "model")
            if name and not isinstance(name, (int, float)):
                return str(name)
    return ""


def _almacenamiento_gb(computer: Dict[str, Any]) -> Optional[int]:
    """Total de disco en GB a partir de `storages.DISKSIZE` (OCS lo guarda en MB).

    Devuelve `int` porque el campo del modelo es `PositiveIntegerField`; devolver
    un float aquí solo funcionaba por el `int()` que Django aplica al guardar
    (476.9 quedaba truncado a 476 en la BD).
    """
    total_mb = 0.0
    for storage in _lista(computer, "storages"):
        try:
            total_mb += float(_get_ci(storage, "disksize", default=0) or 0)
        except (TypeError, ValueError):
            continue
    return int(round(total_mb / 1024)) or None


def _extract_equipo_data(ocs_computer: Dict) -> Dict:
    """Extrae datos relevantes de la respuesta de OCS.

    `id_ocs` es `unique=True`: si OCS no enviara identificador, todos los
    equipos se escribirían sobre el mismo registro. Por eso hay una clave
    derivada como último recurso.
    """
    computer = ocs_computer if isinstance(ocs_computer, dict) else {}
    hardware = _section(computer, "hardware")
    bios = _section(computer, "bios")

    networks = _lista(computer, "networks")
    mac_address, ip_address = _red_principal(hardware, networks)

    try:
        memory_mb = int(_get_ci(hardware, "memory", default=0) or 0) or None
    except (TypeError, ValueError):
        memory_mb = None

    # OCS no manda `user` en la raíz: el usuario del último reporte va en
    # `hardware.USERID` y el dominio en `hardware.WORKGROUP`.
    usuario = _get_ci(computer, "user") or _get_ci(hardware, "userid")
    dominio = _get_ci(hardware, "userdomain", "workgroup")

    # OCS no manda `id` en la raíz: el ID vive en `accountinfo.ID` y
    # `hardware.ID`. El cliente además lo inyecta desde la clave del dict.
    id_ocs = str(_get_ci(computer, "id", "deviceid") or _get_ci(hardware, "id", "deviceid") or "")
    if not id_ocs:
        id_ocs = f"sin-id:{_get_ci(computer, 'name') or 'desconocido'}:{mac_address}"
        logger.warning(
            f"OCS no devolvió ID ni DEVICEID; se genera una clave derivada: {id_ocs}"
        )

    return {
        "id_ocs": id_ocs,
        "nombre_host": _get_ci(computer, "name") or _get_ci(hardware, "name") or "(sin nombre)",
        "usuario_dominio": f"{dominio}\\{usuario}" if dominio and usuario else (usuario or dominio or ""),
        "so_nombre": _get_ci(hardware, "osname"),
        "so_version": _get_ci(hardware, "osversion"),
        "procesador": _procesador(hardware, computer),
        "memoria_ram_mb": memory_mb,
        "almacenamiento_total_gb": _almacenamiento_gb(computer),
        # OCS 2.12 usa `SSN` como número de serie del sistema.
        "serial_bios": _get_ci(bios, "ssn", "sn", "msn", "serial"),
        "mac_address": mac_address,
        "ip_address": ip_address,
        # Fecha real del inventario en OCS, no la hora del sync: antes ponía
        # `datetime.now()` y la UI mostraba "reportó ahora" para equipos que
        # nunca habían reportado.
        "ultimo_reporte_ocs": _parse_ocs_datetime(
            _get_ci(computer, "lastcome", "lastinventory")
            or _get_ci(hardware, "lastcome", "lastinventory")
        ),
    }


def _sincronizar_software_tras_equipos(usuario=None) -> None:
    """Lee el software de los activos recién vinculados, best-effort.

    Va detrás del sync de equipos y no dentro de su transacción: si OCS se cae
    a mitad, el inventario de hardware ya quedó guardado y este paso solo
    agrega filas de software. Perder el software de una vuelta es preferible a
    perder la vinculación de los equipos.

    Solo corre para los equipos que OCS acaba de reportar. Los que ya estaban
    conocidos no se vuelven a leer acá: con la flota completa son N requests
    extra en cada vuelta, que es lo que `sincronizar_software` hace aparte y
    con su propio horario.
    """
    from inventario.sync_software import sincronizar_software

    # Un equipo necesita software si su activo no tiene ninguna fila guardada
    # todavía. El related_name evita importar el modelo.
    activos = list(
        EquipoOCS.objects.exclude(activo_local__isnull=True)
        .exclude(activo_local__estado="dado_de_baja")
        .exclude(activo_local__software_instalado__isnull=False)
        .select_related("activo_local")
        .distinct()
    )
    if not activos:
        return

    try:
        resumen = sincronizar_software([e.activo_local for e in activos])
    except Exception:
        logger.warning("No se pudo leer el software tras el sync de equipos", exc_info=True)
        return
    logger.info("Software tras sync de equipos: %s activos leídos", resumen["leidos"])


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

        # Los equipos ya quedaron guardados; ahora el software de los que
        # todavía no tienen nada. Va después de guardar el log para que un fallo
        # acá no rompa el estado de la sincronización de hardware.
        fecha_fin = timezone.now()
        log.fecha_fin = fecha_fin
        log.duracion_segundos = int((fecha_fin - fecha_inicio).total_seconds())
        log.save()

        _sincronizar_software_tras_equipos(usuario=usuario)

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


def _normaliza_mac(valor: Any) -> str:
    """Deja una MAC como 12 dígitos hexadecimales en mayúscula.

    El inventario local guarda las MAC con guiones ("9C-B1-50-8C-29-2X") y OCS
    las devuelve con dos puntos ("E8:CF:83:0A:8C:0E"). Un `icontains` entre ambos
    formatos nunca acierta, por eso la comparación se hace sobre la forma
    normalizada. Se ignoran los separadores porque no siempre están en el mismo
    sitio: hay captura de pantalla donde el último grupo sale partido.
    """
    if not valor:
        return ""
    limpio = "".join(c for c in str(valor).upper() if c in "0123456789ABCDEF")
    return limpio if len(limpio) == 12 else ""


def buscar_posibles_matches(equipo: EquipoOCS, por_serial: bool = True,
                            por_mac: bool = True,
                            por_hostname: bool = True) -> List[Tuple[Any, List[str]]]:
    """
    Busca posibles coincidencias en inventario local.

    Antes esta función solo miraba el serial con `icontains` y devolvía una lista
    plana de activos, sin explicar por qué proponía cada uno. Eso producía dos
    fallos en cadena: la lista salía vacía en los casos que más la necesitan, y
    cuando salía, el usuario no tenía forma de saber si la sugerencia era una
    coincidencia real o un simple parecido. Ahora devuelve tuplas
    ``(activo, motivos)`` ordenadas por fuerza de la coincidencia.

    Args:
        equipo: EquipoOCS a buscar
        por_serial: Buscar por serial BIOS
        por_mac: Buscar por MAC address
        por_hostname: Buscar por hostname

    Returns:
        Lista de ``(activo, motivos)``. Un activo ya vinculado a otro equipo OCS
        se excluye: ocupa su lugar y proponerlo solo genera errores.
    """
    from inventario.models import Activo

    # Los identificadores del equipo, normalizados una sola vez
    host = (equipo.nombre_host or "").strip()
    serial = (equipo.serial_bios or "").strip()
    mac = _normaliza_mac(equipo.mac_address)

    # Activos que ya están ocupados por OTRO equipo de OCS. Se resuelve en una
    # sola consulta porque _anotar se llama por cada candidato.
    ocupados = set(
        EquipoOCS.objects.exclude(pk=equipo.pk)
        .exclude(activo_local__isnull=True)
        .values_list("activo_local_id", flat=True)
    )

    # Un mismo activo puede aparecer por varias reglas: se acumula el motivo.
    motivos_por_id: Dict[int, List[str]] = {}
    orden: List[int] = []

    def _anotar(activo, motivo: str) -> None:
        if activo.pk in ocupados:
            return
        if activo.pk not in motivos_por_id:
            motivos_por_id[activo.pk] = []
            orden.append(activo.pk)
        if motivo not in motivos_por_id[activo.pk]:
            motivos_por_id[activo.pk].append(motivo)

    # Serial: coincidencia exacta primero, porque es el identificador fuerte.
    if por_serial and serial:
        for activo in Activo.objects.filter(serial__iexact=serial):
            _anotar(activo, "serial del BIOS idéntico")
        for activo in Activo.objects.filter(serial__icontains=serial).exclude(serial__iexact=serial):
            _anotar(activo, "el serial del inventario contiene el del BIOS")

    # MAC: se recuperan candidatos por un fragmento y se compara ya normalizada,
    # porque el separador local y el de OCS no coinciden. El fragmento tiene que
    # ser un trozo que exista literalmente en el texto guardado: con "8C0E" no
    # encuentra nada en "E8-CF-83-0A-8C-0E", porque el guion parte el grupo. Por
    # eso se usa el último octeto, que sobrevive a cualquier formato. Es un
    # filtro débil a propósito: la exactitud la pone la comparación normalizada
    # de abajo, no este icontains.
    if por_mac and mac:
        ultimo_octeto = mac[-2:]
        for activo in Activo.objects.filter(mac_equipo__icontains=ultimo_octeto):
            if _normaliza_mac(activo.mac_equipo) == mac:
                _anotar(activo, "misma MAC de red")

    # Hostname: se busca en el campo que lo contiene. Va también en `serial`
    # porque es un error de captura frecuente (hostname en el campo del service
    # tag) y es justo el caso que hacía falta resolver.
    if por_hostname and host:
        for activo in Activo.objects.filter(nombre_equipo__iexact=host):
            _anotar(activo, "mismo nombre de equipo")
        for activo in Activo.objects.filter(nombre_equipo__icontains=host).exclude(nombre_equipo__iexact=host):
            _anotar(activo, "el nombre de equipo contiene el del OCS")
        for activo in Activo.objects.filter(serial__iexact=host):
            _anotar(activo, "el hostname está en el campo serial del activo")
        for activo in Activo.objects.filter(observaciones__icontains=host):
            _anotar(activo, "el hostname aparece en las observaciones")

    if not orden:
        return []

    # Un activo con más de un motivo independiente es la sugerencia más fuerte.
    candidatos = {a.pk: a for a in Activo.objects.filter(pk__in=orden)}

    def _fuerza(item):
        _, motivos = item
        return (-len(motivos), motivos)

    return sorted(
        ((candidatos[pk], motivos_por_id[pk]) for pk in orden),
        key=_fuerza,
    )
