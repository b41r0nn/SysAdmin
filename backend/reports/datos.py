"""Columnas exportables y cálculos de los reportes."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone

from inventario.models import Activo, Movimiento, TIPOS, ESTADOS
from usuarios.models import Usuario




# Mapeo de columnas disponibles para exportar inventario.
# Cada entrada: key: (label, extractor(activo, asignacion_activa))
# El orden define el orden de columnas en el reporte completo.
CAMPOS_INVENTARIO = {
    # ── Comunes ──────────────────────────────────────────────────────────────
    "id": ("ID", lambda a, asig: a.id),
    "tipo": ("Tipo de dispositivo", lambda a, asig: a.get_tipo_dispositivo_display()),
    "marca": ("Marca", lambda a, asig: a.marca),
    "modelo": ("Modelo", lambda a, asig: a.modelo),
    "serial": ("Serial", lambda a, asig: a.serial),
    "estado": ("Estado", lambda a, asig: a.get_estado_display()),
    "ubicacion": ("Ubicación física", lambda a, asig: a.ubicacion_fisica),
    "fecha_compra": ("Fecha de compra", lambda a, asig: a.fecha_compra.strftime("%Y-%m-%d") if a.fecha_compra else ""),
    "proveedor": ("Proveedor", lambda a, asig: a.proveedor),
    "valor_compra": ("Valor de compra", lambda a, asig: float(a.valor_compra) if a.valor_compra else None),
    "garantia_meses": ("Garantía fábrica (meses)", lambda a, asig: a.garantia_fabrica_meses),
    "garantia_extendida": ("Garantía extendida", lambda a, asig: "Sí" if a.garantia_extendida else "No"),
    "garantia_anos": ("Años garantía extendida", lambda a, asig: a.anios_garantia_extendida),
    "en_garantia": ("En garantía", lambda a, asig: "Sí" if a.en_garantia else "No"),
    "fecha_vencimiento_garantia": ("Fecha vencimiento garantía", lambda a, asig: a.fecha_vencimiento_garantia.strftime("%Y-%m-%d") if a.fecha_vencimiento_garantia else ""),
    "observaciones": ("Observaciones", lambda a, asig: a.observaciones),
    # ── Escritorio / Portátil ────────────────────────────────────────────────
    "nombre_equipo": ("Nombre del equipo", lambda a, asig: getattr(a, "nombre_equipo", "") or ""),
    "disco_capacidad": ("Capacidad disco", lambda a, asig: a.disco_capacidad),
    "tipo_disco": ("Tipo de disco", lambda a, asig: a.tipo_disco),
    "ram": ("RAM", lambda a, asig: a.ram),
    "procesador": ("Procesador", lambda a, asig: a.procesador),
    "sistema_operativo": ("Sistema operativo", lambda a, asig: a.sistema_operativo),
    "licencia_so": ("Licencia SO", lambda a, asig: a.licencia_so),
    "usuario_red": ("Usuario de red", lambda a, asig: a.usuario_red),
    "usuario_admin_local": ("Admin local", lambda a, asig: a.usuario_admin_local),
    "ip_equipo": ("IP del equipo", lambda a, asig: a.ip_equipo or ""),
    "mac_equipo": ("MAC del equipo", lambda a, asig: a.mac_equipo),
    # ── Celular ───────────────────────────────────────────────────────────────
    "imei": ("IMEI", lambda a, asig: a.imei or ""),
    "almacenamiento": ("Almacenamiento", lambda a, asig: a.almacenamiento),
    "ram_celular": ("RAM (celular)", lambda a, asig: a.ram_celular),
    "procesador_celular": ("Procesador (celular)", lambda a, asig: a.procesador_celular),
    "tipo_disco_celular": ("Tipo de disco (celular)", lambda a, asig: a.tipo_disco_celular),
    "cuenta_correo_dispositivo": ("Correo dispositivo", lambda a, asig: a.cuenta_correo_dispositivo),
    "numero_linea": ("Número de línea", lambda a, asig: a.numero_linea),
    "operador": ("Operador", lambda a, asig: a.operador),
    # ── Teléfono fijo ─────────────────────────────────────────────────────────
    "extension": ("Extensión", lambda a, asig: a.extension),
    "puerto_jack": ("Puerto / Jack", lambda a, asig: a.puerto_jack),
    "linea_asignada": ("Línea asignada", lambda a, asig: a.linea_asignada),
    # ── Monitor ───────────────────────────────────────────────────────────────
    "pulgadas": ("Pulgadas", lambda a, asig: float(a.pulgadas) if a.pulgadas else None),
    "resolucion": ("Resolución", lambda a, asig: a.resolucion),
    "tipo_panel": ("Tipo de panel", lambda a, asig: a.tipo_panel),
    "conectores": ("Conectores", lambda a, asig: a.conectores),
    # ── Asignación ────────────────────────────────────────────────────────────
    "asignado_a": ("Asignado a", lambda a, asig: asig.usuario.nombre_completo if asig else ""),
    "documento_usuario": ("Documento usuario", lambda a, asig: asig.usuario.documento_identidad if asig else ""),
    "area_usuario": ("Área usuario", lambda a, asig: asig.usuario.area if asig else ""),
    "fecha_asignacion": ("Fecha asignación", lambda a, asig: asig.fecha_asignacion.strftime("%Y-%m-%d") if asig else ""),
    # ── Metadatos ─────────────────────────────────────────────────────────────
    "fecha_creacion": ("Fecha creación", lambda a, asig: a.fecha_creacion.strftime("%Y-%m-%d %H:%M")),
    "ultima_actualizacion": ("Última actualización", lambda a, asig: a.fecha_actualizacion.strftime("%Y-%m-%d %H:%M")),
}


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _shift_months(base_date, delta_months):
    year = base_date.year + (base_date.month - 1 + delta_months) // 12
    month = (base_date.month - 1 + delta_months) % 12 + 1
    return date(year, month, 1)


def _months_between(start_date, end_date):
    if start_date is None:
        return 0
    months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
    if end_date.day < start_date.day:
        months -= 1
    return max(months, 0)


def _build_activos_resumen():
    estados_map = dict(ESTADOS)
    tipos_map = dict(TIPOS)

    estados_counts = {key: 0 for key, _ in ESTADOS}
    for row in Activo.objects.values("estado").annotate(total=Count("id")):
        estados_counts[row["estado"]] = row["total"]

    tipos_counts = {key: 0 for key, _ in TIPOS}
    for row in Activo.objects.values("tipo_dispositivo").annotate(total=Count("id")):
        tipos_counts[row["tipo_dispositivo"]] = row["total"]

    activos_por_estado = [
        {"key": key, "label": estados_map.get(key, key), "total": total}
        for key, total in estados_counts.items()
    ]
    activos_por_tipo = [
        {"key": key, "label": tipos_map.get(key, key), "total": total}
        for key, total in tipos_counts.items()
    ]

    return activos_por_estado, activos_por_tipo


def _build_movimientos_mensuales(rango_fin):
    rango_inicio = _shift_months(rango_fin.replace(day=1), -11)
    qs = (
        Movimiento.objects.filter(fecha__gte=rango_inicio, fecha__lte=rango_fin)
        .annotate(mes=TruncMonth("fecha"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )
    totales = {}
    for row in qs:
        mes = row["mes"]
        if hasattr(mes, "date"):
            mes = mes.date()
        totales[mes] = row["total"]

    meses = []
    for offset in range(12):
        mes = _shift_months(rango_inicio, offset)
        meses.append({"mes": mes, "total": totales.get(mes, 0)})
    return meses


def _build_costos(rango_fin, vida_util_meses=36):
    total = Decimal("0")
    depreciacion = Decimal("0")
    valor_actual = Decimal("0")
    items = []

    activos = Activo.objects.exclude(valor_compra__isnull=True).order_by("-valor_compra")
    for activo in activos:
        valor = activo.valor_compra or Decimal("0")
        meses = _months_between(activo.fecha_compra, rango_fin)
        meses = min(meses, vida_util_meses)
        if vida_util_meses > 0:
            dep = (valor * Decimal(meses) / Decimal(vida_util_meses)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            dep = Decimal("0.00")
        actual = (valor - dep).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        total += valor
        depreciacion += dep
        valor_actual += actual

        items.append({
            "activo": activo,
            "valor": valor,
            "depreciacion": dep,
            "valor_actual": actual,
            "meses": meses,
        })

    items.sort(key=lambda item: item["valor_actual"], reverse=True)
    return {
        "total": total,
        "depreciacion": depreciacion,
        "valor_actual": valor_actual,
        "items": items[:8],
        "vida_util": vida_util_meses,
    }


def _build_garantias():
    """Lista de activos con fecha de vencimiento de garantía calculable.

    Usa campos existentes (fecha_compra, garantia_fabrica_meses,
    garantia_extendida, anios_garantia_extendida, proveedor). La fecha fin
    de garantía es la property Activo.fecha_vencimiento_garantia.
    Devuelve (vencidos, vigentes), cada uno ordenado por días restantes
    ascendente (vencidos = los más vencidos primero, con días negativos).
    """
    hoy = timezone.now().date()
    items = []
    for activo in Activo.objects.exclude(fecha_compra__isnull=True):
        vencimiento = activo.fecha_vencimiento_garantia
        if vencimiento is None:
            continue
        items.append({
            "activo": activo,
            "vencimiento": vencimiento,
            "dias_restantes": (vencimiento - hoy).days,
        })

    vencidos = sorted(
        (i for i in items if i["dias_restantes"] < 0),
        key=lambda i: i["dias_restantes"],
    )
    vigentes = sorted(
        (i for i in items if i["dias_restantes"] >= 0),
        key=lambda i: i["dias_restantes"],
    )
    return vencidos, vigentes


def _build_report_context(rango_inicio, rango_fin):
    activos_por_estado, activos_por_tipo = _build_activos_resumen()
    movimientos_mensuales = _build_movimientos_mensuales(rango_fin)
    costos = _build_costos(rango_fin)

    usuarios_activos = Usuario.objects.filter(estado="activo").count()
    usuarios_inactivos = Usuario.objects.filter(estado="inactivo").count()
    usuarios_por_area = (
        Usuario.objects.values("area")
        .annotate(total=Count("id"))
        .order_by("-total", "area")
    )

    movimientos_qs = (
        Movimiento.objects.filter(fecha__range=(rango_inicio, rango_fin))
        .select_related("activo", "usuario_destino")
        .order_by("-fecha", "-fecha_creacion")
    )

    garantia_vencidos, garantia_vigentes = _build_garantias()

    activos_total = sum(item["total"] for item in activos_por_estado)

    return {
        "rango_inicio": rango_inicio,
        "rango_fin": rango_fin,
        "usuarios_activos": usuarios_activos,
        "usuarios_inactivos": usuarios_inactivos,
        "usuarios_por_area": usuarios_por_area,
        "activos_total": activos_total,
        "activos_por_estado": activos_por_estado,
        "activos_por_tipo": activos_por_tipo,
        "movimientos_total": movimientos_qs.count(),
        "movimientos": movimientos_qs[:50],
        "movimientos_mensuales": movimientos_mensuales,
        "costos_total": costos["total"],
        "costos_depreciacion": costos["depreciacion"],
        "costos_valor_actual": costos["valor_actual"],
        "costos_items": costos["items"],
        "costos_vida_util": costos["vida_util"],
        "activos_por_lugar": (
            Activo.objects.exclude(ubicacion_fisica="")
            .values("ubicacion_fisica")
            .annotate(total=Count("id"))
            .order_by("-total", "ubicacion_fisica")
        ),
        "garantia_vencidos": garantia_vencidos,
        "garantia_vigentes": garantia_vigentes,
    }
