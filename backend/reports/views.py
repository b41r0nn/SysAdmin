from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import os
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.safestring import mark_safe
import weasyprint
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.units import pixels_to_EMU
from PIL import Image as PILImage

from inventario.models import Activo, Asignacion, Movimiento, TIPOS, ESTADOS
from mantenimiento.models import OrdenMantenimiento
from usuarios.models import Usuario


# ── Paleta corporativa REDIHOS ───────────────────────────────────────────────
AZUL = "0156A6"
AZUL_OSCURO = "013D7A"
AZUL_CLARO = "E6F0FA"
NARANJA = "F18020"
GRIS_TXT = "1F2937"
BLANCO = "FFFFFF"

LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "img", "logo_redihos_mark.png")


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

    return {
        "rango_inicio": rango_inicio,
        "rango_fin": rango_fin,
        "usuarios_activos": usuarios_activos,
        "usuarios_inactivos": usuarios_inactivos,
        "usuarios_por_area": usuarios_por_area,
        "activos_total": Activo.objects.count(),
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
    }


# ── Helpers de estilo Excel REDIHOS ──────────────────────────────────────────

def _add_redihos_logo(ws, logo_path=LOGO_PATH):
    """Inserta el logo de REDIHOS centrado en el área combinada A1:B1."""
    if not os.path.exists(logo_path):
        return

    img = XLImage(logo_path)
    with PILImage.open(logo_path) as pil_img:
        w, h = pil_img.size
    img.height = 42
    img.width = int(42 * (w / h))

    # Área disponible: columnas A+B combinadas, fila 1.
    # Aproximación: 1 unidad de ancho de columna ≈ 7 px; 1 punto de alto ≈ 4/3 px.
    col_a_width = ws.column_dimensions["A"].width or 10
    col_b_width = ws.column_dimensions["B"].width or 10
    available_width_px = (col_a_width + col_b_width) * 7

    row_height_pts = ws.row_dimensions[1].height or 48
    available_height_px = row_height_pts * 4 / 3

    off_x = max(0, int((available_width_px - img.width) / 2))
    off_y = max(0, int((available_height_px - img.height) / 2))

    img.anchor = OneCellAnchor(
        _from=AnchorMarker(
            col=0, colOff=pixels_to_EMU(off_x),
            row=0, rowOff=pixels_to_EMU(off_y),
        ),
        ext=XDRPositiveSize2D(cx=pixels_to_EMU(img.width), cy=pixels_to_EMU(img.height)),
    )
    ws.add_image(img, "A1")


def _apply_redihos_header(ws, headers, title, logo_path=LOGO_PATH):
    """
    Escribe el encabezado corporativo (filas 1-4) y los headers de tabla (fila 6).
    Retorna la fila inicial para datos: 7.
    """
    last_col = get_column_letter(len(headers))
    fecha = timezone.now().strftime("%d/%m/%Y")

    banner_fill = PatternFill(start_color=AZUL_OSCURO, end_color=AZUL_OSCURO, fill_type="solid")
    banner_font = Font(name="Calibri", bold=True, size=16, color=BLANCO)
    subtitle_fill = PatternFill(start_color=AZUL_CLARO, end_color=AZUL_CLARO, fill_type="solid")
    subtitle_font = Font(name="Calibri", bold=True, size=12, color=AZUL_OSCURO)
    accent_fill = PatternFill(start_color=NARANJA, end_color=NARANJA, fill_type="solid")
    meta_font = Font(name="Calibri", italic=True, size=9, color="6B7280")
    header_fill = PatternFill(start_color=AZUL, end_color=AZUL, fill_type="solid")
    header_font = Font(name="Calibri", bold=True, size=10, color=BLANCO)
    thin_side = Side(style="thin", color="D1D5DB")
    border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    # Filas 1-4: encabezado corporativo.
    # Columnas A y B se reservan para el logo; el texto arranca en C.
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 10

    # Fila 1: banner
    ws.merge_cells("A1:B1")
    ws.merge_cells(f"C1:{last_col}1")
    ws["C1"] = "REDIHOS S.A.S."
    ws["C1"].fill = banner_fill
    ws["C1"].font = banner_font
    ws["C1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 48
    _add_redihos_logo(ws, logo_path)

    # Fila 2: subtítulo
    ws.merge_cells(f"C2:{last_col}2")
    ws["C2"] = f"Reporte de {title}"
    ws["C2"].fill = subtitle_fill
    ws["C2"].font = subtitle_font
    ws["C2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 22

    # Fila 3: franja naranja (completa, incluyendo zona del logo)
    ws.merge_cells(f"A3:{last_col}3")
    for col in range(1, len(headers) + 1):
        ws.cell(row=3, column=col).fill = accent_fill
    ws.row_dimensions[3].height = 4

    # Fila 4: metadato
    ws.merge_cells(f"C4:{last_col}4")
    ws["C4"] = f"Generado por SysAdmin · {fecha} · Confidencial — uso interno"
    ws["C4"].font = meta_font
    ws["C4"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[4].height = 16

    # Fila 6: headers de tabla
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=6, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[6].height = 26

    # Freeze panes en primera celda de datos
    ws.freeze_panes = "A8"

    # Auto filter sobre header
    ws.auto_filter.ref = f"A6:{last_col}6"

    return 7


def _apply_redihos_data_style(ws, start_row, num_cols):
    """Aplica zebra striping, bordes y tipografía a las filas de datos."""
    data_font = Font(name="Calibri", size=10, color=GRIS_TXT)
    white_fill = PatternFill(start_color=BLANCO, end_color=BLANCO, fill_type="solid")
    blue_light_fill = PatternFill(start_color=AZUL_CLARO, end_color=AZUL_CLARO, fill_type="solid")
    thin_side = Side(style="thin", color="D1D5DB")
    border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    for row_idx in range(start_row, ws.max_row + 1):
        fill = white_fill if (row_idx - start_row) % 2 == 0 else blue_light_fill
        for col_idx in range(1, num_cols + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = data_font
            cell.fill = fill
            cell.border = border
            cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)


def _adjust_column_widths(ws, headers, data_end_row=None, min_width=12, max_width=55):
    """Ajusta el ancho de cada columna al contenido real.

    Si `data_end_row` se proporciona, solo se mide hasta esa fila (útil para no
    incluir secciones de resumen que puedan inflar columnas como la A).
    """
    max_row = data_end_row if data_end_row is not None else min(ws.max_row, 7 + 200)
    for col_idx, header in enumerate(headers, start=1):
        col_letter = get_column_letter(col_idx)
        max_len = len(str(header))
        for row in ws.iter_rows(
            min_row=7,
            max_row=max_row,
            min_col=col_idx,
            max_col=col_idx,
        ):
            for cell in row:
                val = cell.value
                if val is not None:
                    max_len = max(max_len, len(str(val)))
        width = min(max(max_len + 4, min_width), max_width)
        ws.column_dimensions[col_letter].width = width


def _style_summary_sheet(ws, title):
    """Aplica solo el encabezado corporativo a una hoja de resumen (sin tabla)."""
    last_col = "B"
    fecha = timezone.now().strftime("%d/%m/%Y")

    banner_fill = PatternFill(start_color=AZUL_OSCURO, end_color=AZUL_OSCURO, fill_type="solid")
    banner_font = Font(name="Calibri", bold=True, size=16, color=BLANCO)
    subtitle_fill = PatternFill(start_color=AZUL_CLARO, end_color=AZUL_CLARO, fill_type="solid")
    subtitle_font = Font(name="Calibri", bold=True, size=12, color=AZUL_OSCURO)
    accent_fill = PatternFill(start_color=NARANJA, end_color=NARANJA, fill_type="solid")
    meta_font = Font(name="Calibri", italic=True, size=9, color="6B7280")

    ws.merge_cells(f"A1:{last_col}1")
    ws["A1"] = "REDIHOS S.A.S."
    ws["A1"].fill = banner_fill
    ws["A1"].font = banner_font
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=2)
    ws.row_dimensions[1].height = 32

    ws.merge_cells(f"A2:{last_col}2")
    ws["A2"] = f"Reporte de {title} — Resumen"
    ws["A2"].fill = subtitle_fill
    ws["A2"].font = subtitle_font
    ws["A2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 22

    ws.merge_cells(f"A3:{last_col}3")
    ws["A3"].fill = accent_fill
    ws.row_dimensions[3].height = 4

    ws.merge_cells(f"A4:{last_col}4")
    ws["A4"] = f"Generado por SysAdmin · {fecha} · Confidencial — uso interno"
    ws["A4"].font = meta_font
    ws["A4"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[4].height = 16

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 20


# ── Vistas ───────────────────────────────────────────────────────────────────

@login_required
def index(request):
    today = timezone.now().date()
    rango_fin = _parse_date(request.GET.get("fin")) or today
    rango_inicio = _parse_date(request.GET.get("inicio")) or (rango_fin - timedelta(days=30))
    if rango_inicio > rango_fin:
        rango_inicio, rango_fin = rango_fin, rango_inicio

    context = _build_report_context(rango_inicio, rango_fin)
    return render(request, "reports/index.html", context)


@login_required
def inventario_pdf(request):
    # Selección de columnas
    campos_solicitados = request.GET.getlist("campos")
    campos = [c for c in campos_solicitados if c in CAMPOS_INVENTARIO] or list(CAMPOS_INVENTARIO.keys())

    # Filtro por tipo de dispositivo
    tipos_solicitados = request.GET.getlist("tipos")
    filtrar_por_tipo = tipos_solicitados and "todos" not in tipos_solicitados

    activos_qs = Activo.objects.prefetch_related(
        Prefetch(
            "asignaciones",
            queryset=Asignacion.objects.filter(activa=True).select_related("usuario"),
            to_attr="asignaciones_activas",
        )
    ).order_by("tipo_dispositivo", "marca", "modelo")

    if filtrar_por_tipo:
        activos_qs = activos_qs.filter(tipo_dispositivo__in=tipos_solicitados)

    # Construir filas: cada fila es un activo, cada celda un campo
    filas = []
    for activo in activos_qs:
        asignacion = activo.asignaciones_activas[0] if activo.asignaciones_activas else None
        fila = []
        for c in campos:
            raw = CAMPOS_INVENTARIO[c][1](activo, asignacion)
            if c == "estado":
                valor = mark_safe(f'<span class="badge {activo.estado}">{raw}</span>')
                vacio = False
            elif c == "valor_compra" and raw is not None:
                valor = f"${raw:,.0f} COP"
                vacio = False
            else:
                vacio = raw in (None, "")
                valor = "—" if vacio else raw
            fila.append({"valor": valor, "vacio": vacio})
        filas.append(fila)

    # Podar columnas sin datos en ninguna fila (patrón de Snipe-IT/GLPI:
    # un campo vacío para todo el universo no aporta y ensancha el reporte)
    if filas:
        keep_idx = [
            i for i in range(len(campos))
            if any(not fila[i]["vacio"] for fila in filas)
        ]
        if len(keep_idx) < len(campos):
            campos = [campos[i] for i in keep_idx]
            filas = [[fila[i] for i in keep_idx] for fila in filas]

    columnas_count = len(campos)
    if columnas_count > 25:
        tabla_font = "6pt"
    elif columnas_count > 15:
        tabla_font = "7pt"
    else:
        tabla_font = "8.5pt"

    # Anchos dinámicos según contenido (estilo GLPI Protocols Manager:
    # "dynamic column widths"). El peso usa el token más largo (no la suma
    # de caracteres), porque las celdas envuelven por palabra. Se normaliza
    # a 100% con table-layout: fixed para que nada se salga de la página.
    TOKEN_CAPS = {
        "id": 6, "estado": 15, "valor_compra": 15, "observaciones": 26,
        "fecha_compra": 11, "fecha_vencimiento_garantia": 11,
        "fecha_asignacion": 11, "fecha_creacion": 17,
        "ultima_actualizacion": 17, "documento_usuario": 12,
    }

    def _peso_columna(campo, idx):
        tokens = [t for t in re.split(r"\s+", CAMPOS_INVENTARIO[campo][0]) if t]
        for fila in filas:
            texto = re.sub(r"<[^>]+>", "", str(fila[idx]["valor"]))
            tokens.extend(t for t in re.split(r"\s+", texto) if t)
        mayor = max((len(t) for t in tokens), default=4)
        cap = TOKEN_CAPS.get(campo, 22)
        return min(max(mayor + 1, 6), cap)

    pesos = [_peso_columna(c, idx) for idx, c in enumerate(campos)]
    total_peso = sum(pesos) or 1
    columnas = [
        {
            "key": c,
            "label": CAMPOS_INVENTARIO[c][0],
            "ancho": round(pesos[idx] / total_peso * 100, 2),
        }
        for idx, c in enumerate(campos)
    ]

    tipos_a_resumir = (
        [(key, label) for key, label in TIPOS if key in tipos_solicitados]
        if filtrar_por_tipo else TIPOS
    )
    resumen = []
    for key, label in tipos_a_resumir:
        qs = activos_qs.filter(tipo_dispositivo=key)
        resumen.append({
            "label": label,
            "total": qs.count(),
            "disponibles": qs.filter(estado="disponible").count(),
            "asignados": qs.filter(estado="asignado").count(),
            "mantenimiento": qs.filter(estado="en_mantenimiento").count(),
            "reparacion": qs.filter(estado="en_reparacion").count(),
            "baja": qs.filter(estado="dado_de_baja").count(),
        })

    totales = {"activos": activos_qs.count()}
    if "valor_compra" in campos:
        total_valor = sum(
            (a.valor_compra or Decimal("0")) for a in activos_qs.exclude(valor_compra__isnull=True)
        )
        totales["valor"] = f"${total_valor:,.0f} COP"
    if "estado" in campos:
        totales["estado"] = {
            "disponibles": activos_qs.filter(estado="disponible").count(),
            "asignados": activos_qs.filter(estado="asignado").count(),
            "mantenimiento": activos_qs.filter(estado="en_mantenimiento").count(),
            "reparacion": activos_qs.filter(estado="en_reparacion").count(),
            "baja": activos_qs.filter(estado="dado_de_baja").count(),
        }

    html_string = render_to_string("reports/inventario_pdf.html", {
        "columnas": columnas,
        "filas": filas,
        "resumen": resumen,
        "totales": totales,
        "campos": campos,
        "tabla_font": tabla_font,
        "logo_path": LOGO_PATH,
        "generado": timezone.now(),
    })
    pdf_bytes = weasyprint.HTML(
        string=html_string, base_url=request.build_absolute_uri("/")
    ).write_pdf()

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="reporte_inventario.pdf"'
    return response


@login_required
def usuarios_pdf(request):
    usuarios = (
        Usuario.objects.annotate(
            activos_asignados=Count("asignaciones", filter=Q(asignaciones__activa=True))
        )
        .order_by("nombre_completo")
    )
    context = {
        "fecha_generacion": timezone.now(),
        "usuarios": usuarios,
    }

    html_string = render_to_string("reports/usuarios_pdf.html", context)
    pdf_bytes = weasyprint.HTML(
        string=html_string, base_url=request.build_absolute_uri("/")
    ).write_pdf()

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="reporte_usuarios.pdf"'
    return response


@login_required
def inventario_excel(request):
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventario"

    # Selección de columnas
    campos_solicitados = request.GET.getlist("campos")
    if campos_solicitados:
        campos = [c for c in campos_solicitados if c in CAMPOS_INVENTARIO]
    else:
        campos = list(CAMPOS_INVENTARIO.keys())

    # Filtro por tipo de dispositivo
    tipos_solicitados = request.GET.getlist("tipos")
    filtrar_por_tipo = tipos_solicitados and "todos" not in tipos_solicitados
    tipos_a_resumir = (
        [(key, label) for key, label in TIPOS if key in tipos_solicitados]
        if filtrar_por_tipo else TIPOS
    )

    headers = [CAMPOS_INVENTARIO[c][0] for c in campos]
    last_col_letter = get_column_letter(len(headers))
    start_row = _apply_redihos_header(ws, headers, "Inventario")

    activos = Activo.objects.prefetch_related(
        Prefetch(
            "asignaciones",
            queryset=Asignacion.objects.filter(activa=True).select_related("usuario"),
            to_attr="asignaciones_activas",
        )
    ).order_by("tipo_dispositivo", "marca", "modelo")

    if filtrar_por_tipo:
        activos = activos.filter(tipo_dispositivo__in=tipos_solicitados)

    for row_idx, activo in enumerate(activos, start=start_row):
        asignacion = activo.asignaciones_activas[0] if activo.asignaciones_activas else None
        row = [CAMPOS_INVENTARIO[c][1](activo, asignacion) for c in campos]
        ws.append(row)

    _apply_redihos_data_style(ws, start_row, len(headers))

    # Formato monetario para valor_compra si está presente
    if "valor_compra" in campos:
        valor_col = campos.index("valor_compra") + 1
        for row_idx in range(start_row, ws.max_row + 1):
            ws.cell(row=row_idx, column=valor_col).number_format = '$#,##0'

    # ── Resumen por categorías (tipo de dispositivo) ─────────────────────────
    thin_side = Side(style="thin", color="D1D5DB")
    border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    data_font = Font(name="Calibri", size=10, color=GRIS_TXT)
    white_fill = PatternFill(start_color=BLANCO, end_color=BLANCO, fill_type="solid")
    blue_light_fill = PatternFill(start_color=AZUL_CLARO, end_color=AZUL_CLARO, fill_type="solid")
    section_title_font = Font(name="Calibri", bold=True, size=12, color=AZUL_OSCURO)
    section_title_fill = PatternFill(start_color=AZUL_CLARO, end_color=AZUL_CLARO, fill_type="solid")
    header_fill = PatternFill(start_color=AZUL, end_color=AZUL, fill_type="solid")
    header_font = Font(name="Calibri", bold=True, size=10, color=BLANCO)

    resumen_start = ws.max_row + 3
    ws.merge_cells(f"A{resumen_start}:{last_col_letter}{resumen_start}")
    title_cell = ws.cell(row=resumen_start, column=1, value="Resumen por categorías")
    title_cell.font = section_title_font
    title_cell.fill = section_title_fill
    title_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[resumen_start].height = 22

    resumen_headers = [
        "Categoría", "Total", "Disponibles", "Asignados",
        "En mantenimiento", "En reparación", "Dados de baja"
    ]
    header_row = resumen_start + 1
    for col_idx, h in enumerate(resumen_headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[header_row].height = 26

    data_start = header_row + 1
    for idx, (key, label) in enumerate(tipos_a_resumir, start=data_start):
        qs = activos.filter(tipo_dispositivo=key)
        values = [
            label,
            qs.count(),
            qs.filter(estado="disponible").count(),
            qs.filter(estado="asignado").count(),
            qs.filter(estado="en_mantenimiento").count(),
            qs.filter(estado="en_reparacion").count(),
            qs.filter(estado="dado_de_baja").count(),
        ]
        fill = white_fill if (idx - data_start) % 2 == 0 else blue_light_fill
        for col_idx, val in enumerate(values, start=1):
            cell = ws.cell(row=idx, column=col_idx, value=val)
            cell.font = data_font
            cell.fill = fill
            cell.border = border
            cell.alignment = Alignment(
                horizontal="left" if col_idx == 1 else "center",
                vertical="center",
                indent=1
            )

    # ── Fila de totales generales ────────────────────────────────────────────
    totales_font = Font(name="Calibri", bold=True, size=11, color=AZUL_OSCURO)
    totales_fill = PatternFill(start_color=AZUL_CLARO, end_color=AZUL_CLARO, fill_type="solid")
    total_row = ws.max_row + 2

    ws.merge_cells(f"A{total_row}:{last_col_letter}{total_row}")
    total_cell = ws.cell(row=total_row, column=1, value=f"Total de activos: {activos.count()}")
    total_cell.font = totales_font
    total_cell.fill = totales_fill
    total_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[total_row].height = 22

    current_row = total_row + 1

    if "valor_compra" in campos:
        total_valor = sum(
            (a.valor_compra or Decimal("0")) for a in activos.exclude(valor_compra__isnull=True)
        )
        ws.merge_cells(f"A{current_row}:{last_col_letter}{current_row}")
        valor_cell = ws.cell(
            row=current_row, column=1,
            value=f"Valor total inventario: ${total_valor:,.0f} COP"
        )
        valor_cell.font = totales_font
        valor_cell.fill = totales_fill
        valor_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[current_row].height = 22
        current_row += 1

    if "estado" in campos:
        qs = activos
        ws.merge_cells(f"A{current_row}:{last_col_letter}{current_row}")
        estado_cell = ws.cell(
            row=current_row, column=1,
            value=(
                f"Por estado — Disponibles: {qs.filter(estado='disponible').count()} · "
                f"Asignados: {qs.filter(estado='asignado').count()} · "
                f"En mantenimiento: {qs.filter(estado='en_mantenimiento').count()} · "
                f"En reparación: {qs.filter(estado='en_reparacion').count()} · "
                f"Dados de baja: {qs.filter(estado='dado_de_baja').count()}"
            )
        )
        estado_cell.font = totales_font
        estado_cell.fill = totales_fill
        estado_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.row_dimensions[current_row].height = 22

    data_end_row = start_row + activos.count() - 1
    _adjust_column_widths(ws, headers, data_end_row=data_end_row)

    # Asegurar anchos mínimos para las columnas del resumen
    for col_idx, h in enumerate(resumen_headers, start=1):
        col_letter = get_column_letter(col_idx)
        current = ws.column_dimensions[col_letter].width or 12
        ws.column_dimensions[col_letter].width = max(current, len(h) + 4)

    # Configuración de página: horizontal, ajustar ancho y centrado horizontal
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.print_options.verticalCentered = False

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=reporte_inventario.xlsx"
    wb.save(response)
    return response


@login_required
def usuarios_excel(request):
    wb = Workbook()

    usuarios_activos = Usuario.objects.filter(estado="activo").count()
    usuarios_inactivos = Usuario.objects.filter(estado="inactivo").count()
    usuarios_por_area = (
        Usuario.objects.values("area")
        .annotate(total=Count("id"))
        .order_by("-total", "area")
    )
    usuarios_por_cargo = (
        Usuario.objects.values("cargo")
        .annotate(total=Count("id"))
        .order_by("-total", "cargo")
    )

    ws_resumen = wb.active
    ws_resumen.title = "Resumen"
    _style_summary_sheet(ws_resumen, "Usuarios")

    ws_resumen["A6"] = "Usuarios activos"
    ws_resumen["B6"] = usuarios_activos
    ws_resumen["A7"] = "Usuarios inactivos"
    ws_resumen["B7"] = usuarios_inactivos
    ws_resumen["A9"] = "Por area"
    ws_resumen["B9"] = "Total"
    for idx, row in enumerate(usuarios_por_area, start=10):
        ws_resumen.cell(row=idx, column=1, value=row["area"])
        ws_resumen.cell(row=idx, column=2, value=row["total"])
    offset = 10 + len(usuarios_por_area) + 2
    ws_resumen.cell(row=offset, column=1, value="Por cargo")
    ws_resumen.cell(row=offset, column=2, value="Total")
    for idx, row in enumerate(usuarios_por_cargo, start=offset + 1):
        ws_resumen.cell(row=idx, column=1, value=row["cargo"])
        ws_resumen.cell(row=idx, column=2, value=row["total"])

    ws = wb.create_sheet(title="Usuarios")
    headers = [
        "Nombre", "Documento", "Cargo", "Area", "Correo",
        "Telefono", "Estado", "Fecha creacion"
    ]
    start_row = _apply_redihos_header(ws, headers, "Usuarios")

    for usuario in Usuario.objects.all().order_by("nombre_completo"):
        ws.append([
            usuario.nombre_completo,
            usuario.documento_identidad,
            usuario.cargo,
            usuario.area,
            usuario.correo,
            usuario.telefono,
            usuario.get_estado_display(),
            usuario.fecha_creacion.strftime("%Y-%m-%d"),
        ])

    _apply_redihos_data_style(ws, start_row, len(headers))
    _adjust_column_widths(ws, headers)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=reporte_usuarios.xlsx"
    wb.save(response)
    return response


@login_required
def costos_excel(request):
    today = timezone.now().date()
    costos = _build_costos(today)

    wb = Workbook()
    ws_resumen = wb.active
    ws_resumen.title = "Resumen"
    _style_summary_sheet(ws_resumen, "Costos")

    ws_resumen["A6"] = "Vida util (meses)"
    ws_resumen["B6"] = costos["vida_util"]
    ws_resumen["A7"] = "Valor compra total"
    ws_resumen["B7"] = float(costos["total"])
    ws_resumen["A8"] = "Depreciacion acumulada"
    ws_resumen["B8"] = float(costos["depreciacion"])
    ws_resumen["A9"] = "Valor actual estimado"
    ws_resumen["B9"] = float(costos["valor_actual"])

    ws = wb.create_sheet(title="Costos")
    headers = [
        "Activo", "Serial", "Tipo", "Valor compra",
        "Meses", "Depreciacion", "Valor actual"
    ]
    start_row = _apply_redihos_header(ws, headers, "Costos")

    for item in costos["items"]:
        activo = item["activo"]
        ws.append([
            str(activo),
            activo.serial,
            activo.get_tipo_dispositivo_display(),
            float(item["valor"]),
            item["meses"],
            float(item["depreciacion"]),
            float(item["valor_actual"]),
        ])

    _apply_redihos_data_style(ws, start_row, len(headers))
    money_cols = {4, 6, 7}  # columnas con valores monetarios
    for row_idx in range(start_row, ws.max_row + 1):
        for col in money_cols:
            ws.cell(row=row_idx, column=col).number_format = '$#,##0.00'
    _adjust_column_widths(ws, headers)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=reporte_costos.xlsx"
    wb.save(response)
    return response


@login_required
def movimientos_excel(request):
    today = timezone.now().date()
    rango_fin = _parse_date(request.GET.get("fin")) or today
    rango_inicio = _parse_date(request.GET.get("inicio")) or (rango_fin - timedelta(days=30))
    if rango_inicio > rango_fin:
        rango_inicio, rango_fin = rango_fin, rango_inicio

    movimientos = (
        Movimiento.objects.filter(fecha__range=(rango_inicio, rango_fin))
        .select_related("activo", "usuario_destino")
        .order_by("-fecha", "-fecha_creacion")
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Movimientos"
    headers = [
        "Fecha", "Tipo", "Activo", "Serial", "Usuario destino",
        "Descripcion", "Realizado por"
    ]
    start_row = _apply_redihos_header(ws, headers, "Movimientos")

    for mov in movimientos:
        ws.append([
            mov.fecha.strftime("%Y-%m-%d"),
            mov.get_tipo_display(),
            mov.activo.get_tipo_dispositivo_display(),
            mov.activo.serial,
            mov.usuario_destino.nombre_completo if mov.usuario_destino else "",
            mov.descripcion,
            mov.realizado_por,
        ])

    _apply_redihos_data_style(ws, start_row, len(headers))
    _adjust_column_widths(ws, headers)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=reporte_movimientos.xlsx"
    wb.save(response)
    return response


@login_required
def mantenimiento_excel(request):
    today = timezone.now().date()
    rango_fin = _parse_date(request.GET.get("fin")) or today
    rango_inicio = _parse_date(request.GET.get("inicio")) or (rango_fin - timedelta(days=30))
    if rango_inicio > rango_fin:
        rango_inicio, rango_fin = rango_fin, rango_inicio

    ordenes = (
        OrdenMantenimiento.objects.filter(fecha_apertura__range=(rango_inicio, rango_fin))
        .select_related("activo", "plan")
        .order_by("-fecha_apertura", "-fecha_creacion")
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Ordenes"
    headers = [
        "Fecha apertura",
        "Fecha cierre",
        "Tipo",
        "Estado",
        "Prioridad",
        "Activo",
        "Serial",
        "Plan",
        "Tecnico",
        "Costo estimado",
        "Costo real",
    ]
    start_row = _apply_redihos_header(ws, headers, "Mantenimiento")

    for orden in ordenes:
        ws.append([
            orden.fecha_apertura.strftime("%Y-%m-%d") if orden.fecha_apertura else "",
            orden.fecha_cierre.strftime("%Y-%m-%d") if orden.fecha_cierre else "",
            orden.get_tipo_display(),
            orden.get_estado_display(),
            orden.get_prioridad_display(),
            f"{orden.activo.marca} {orden.activo.modelo}",
            orden.activo.serial,
            f"Plan #{orden.plan_id}" if orden.plan_id else "",
            orden.tecnico_asignado,
            float(orden.costo_estimado) if orden.costo_estimado else "",
            float(orden.costo_real) if orden.costo_real else "",
        ])

    _apply_redihos_data_style(ws, start_row, len(headers))
    money_cols = {10, 11}
    for row_idx in range(start_row, ws.max_row + 1):
        for col in money_cols:
            cell = ws.cell(row=row_idx, column=col)
            if isinstance(cell.value, (int, float)):
                cell.number_format = '$#,##0.00'
    _adjust_column_widths(ws, headers)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=reporte_mantenimiento.xlsx"
    wb.save(response)
    return response
