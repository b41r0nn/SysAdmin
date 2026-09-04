from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
import weasyprint
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

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
    """Inserta el logo de REDIHOS en A1 si existe."""
    if os.path.exists(logo_path):
        img = XLImage(logo_path)
        img.width = 28
        img.height = 28
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

    # Fila 1: banner
    ws.merge_cells(f"A1:{last_col}1")
    ws["A1"] = "REDIHOS S.A.S."
    ws["A1"].fill = banner_fill
    ws["A1"].font = banner_font
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=4)
    ws.row_dimensions[1].height = 32
    _add_redihos_logo(ws, logo_path)
    ws.column_dimensions["A"].width = 6

    # Fila 2: subtítulo
    ws.merge_cells(f"A2:{last_col}2")
    ws["A2"] = f"Reporte de {title}"
    ws["A2"].fill = subtitle_fill
    ws["A2"].font = subtitle_font
    ws["A2"].alignment = Alignment(horizontal="left", vertical="center", indent=2)
    ws.row_dimensions[2].height = 22

    # Fila 3: franja naranja
    ws.merge_cells(f"A3:{last_col}3")
    for col in range(1, len(headers) + 1):
        ws.cell(row=3, column=col).fill = accent_fill
    ws.row_dimensions[3].height = 4

    # Fila 4: metadato
    ws.merge_cells(f"A4:{last_col}4")
    ws["A4"] = f"Generado por SysAdmin · {fecha} · Confidencial — uso interno"
    ws["A4"].font = meta_font
    ws["A4"].alignment = Alignment(horizontal="left", vertical="center", indent=2)
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


def _adjust_column_widths(ws, headers, min_width=12, max_width=55):
    """Ajusta el ancho de cada columna al contenido real."""
    for col_idx, header in enumerate(headers, start=1):
        col_letter = get_column_letter(col_idx)
        max_len = len(str(header))
        for row in ws.iter_rows(
            min_row=7,
            max_row=min(ws.max_row, 7 + 200),
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
    today = timezone.now().date()
    context = _build_report_context(today - timedelta(days=30), today)
    activos = Activo.objects.prefetch_related(
        Prefetch(
            "asignaciones",
            queryset=Asignacion.objects.filter(activa=True).select_related("usuario"),
            to_attr="asignaciones_activas",
        )
    ).order_by("estado", "marca", "modelo")

    estados_counts = {key: 0 for key, _ in ESTADOS}
    for row in Activo.objects.values("estado").annotate(total=Count("id")):
        estados_counts[row["estado"]] = row["total"]

    context.update({
        "fecha_generacion": timezone.now(),
        "activos": activos,
        "disponibles": estados_counts.get("disponible", 0),
        "asignados": estados_counts.get("asignado", 0),
        "baja": estados_counts.get("dado_de_baja", 0),
    })

    html_string = render_to_string("reports/inventario_pdf.html", context)
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

    # Hoja de resumen
    ws_resumen = wb.active
    ws_resumen.title = "Resumen"
    _style_summary_sheet(ws_resumen, "Inventario")

    activos_por_estado, activos_por_tipo = _build_activos_resumen()
    ws_resumen["A6"] = "Total activos"
    ws_resumen["B6"] = Activo.objects.count()
    ws_resumen["A7"] = "Por estado"
    ws_resumen["B7"] = "Total"
    for idx, item in enumerate(activos_por_estado, start=8):
        ws_resumen.cell(row=idx, column=1, value=item["label"])
        ws_resumen.cell(row=idx, column=2, value=item["total"])
    offset = 8 + len(activos_por_estado) + 1
    ws_resumen.cell(row=offset, column=1, value="Por tipo")
    ws_resumen.cell(row=offset, column=2, value="Total")
    for idx, item in enumerate(activos_por_tipo, start=offset + 1):
        ws_resumen.cell(row=idx, column=1, value=item["label"])
        ws_resumen.cell(row=idx, column=2, value=item["total"])

    # Hoja de activos
    ws_activos = wb.create_sheet(title="Activos")
    headers = [
        "ID", "Tipo", "Marca", "Modelo", "Serial", "Nombre equipo",
        "Estado", "Ubicacion fisica", "Fecha compra", "Proveedor",
        "Valor compra", "Garantia fabrica (meses)", "Garantia extendida",
        "Anios garantia extendida", "En garantia", "Fecha vencimiento garantia",
        "IMEI", "Almacenamiento", "RAM (celular)", "Procesador (celular)",
        "Tipo disco (celular)", "Correo dispositivo", "Numero linea", "Operador",
        "Disco capacidad", "Tipo disco", "RAM", "Procesador",
        "Sistema operativo", "Licencia SO", "Usuario red", "Usuario admin local",
        "IP equipo", "MAC equipo",
        "Extension", "Puerto jack", "Linea asignada",
        "Pulgadas", "Resolucion", "Tipo panel", "Conectores",
        "Asignado a", "Documento usuario", "Area usuario", "Fecha asignacion",
        "Observaciones", "Fecha creacion", "Ultima actualizacion",
    ]
    start_row = _apply_redihos_header(ws_activos, headers, "Inventario")

    activos = Activo.objects.prefetch_related(
        Prefetch(
            "asignaciones",
            queryset=Asignacion.objects.filter(activa=True).select_related("usuario"),
            to_attr="asignaciones_activas",
        )
    ).order_by("tipo_dispositivo", "marca", "modelo")

    valor_col = headers.index("Valor compra") + 1

    for row_idx, activo in enumerate(activos, start=start_row):
        asignacion = activo.asignaciones_activas[0] if activo.asignaciones_activas else None
        row = [
            activo.id,
            activo.get_tipo_dispositivo_display(),
            activo.marca,
            activo.modelo,
            activo.serial,
            getattr(activo, "nombre_equipo", "") or "",
            activo.get_estado_display(),
            activo.ubicacion_fisica,
            activo.fecha_compra.strftime("%Y-%m-%d") if activo.fecha_compra else "",
            activo.proveedor,
            float(activo.valor_compra) if activo.valor_compra else None,
            activo.garantia_fabrica_meses,
            "Si" if activo.garantia_extendida else "No",
            activo.anios_garantia_extendida,
            "Si" if activo.en_garantia else "No",
            activo.fecha_vencimiento_garantia.strftime("%Y-%m-%d") if activo.fecha_vencimiento_garantia else "",
            activo.imei or "",
            activo.almacenamiento,
            activo.ram_celular,
            activo.procesador_celular,
            activo.tipo_disco_celular,
            activo.cuenta_correo_dispositivo,
            activo.numero_linea,
            activo.operador,
            activo.disco_capacidad,
            activo.tipo_disco,
            activo.ram,
            activo.procesador,
            activo.sistema_operativo,
            activo.licencia_so,
            activo.usuario_red,
            activo.usuario_admin_local,
            activo.ip_equipo or "",
            activo.mac_equipo,
            activo.extension,
            activo.puerto_jack,
            activo.linea_asignada,
            float(activo.pulgadas) if activo.pulgadas else None,
            activo.resolucion,
            activo.tipo_panel,
            activo.conectores,
            asignacion.usuario.nombre_completo if asignacion else "",
            asignacion.usuario.documento_identidad if asignacion else "",
            asignacion.usuario.area if asignacion else "",
            asignacion.fecha_asignacion.strftime("%Y-%m-%d") if asignacion else "",
            activo.observaciones,
            activo.fecha_creacion.strftime("%Y-%m-%d %H:%M"),
            activo.fecha_actualizacion.strftime("%Y-%m-%d %H:%M"),
        ]
        ws_activos.append(row)

    _apply_redihos_data_style(ws_activos, start_row, len(headers))
    for row_idx in range(start_row, ws_activos.max_row + 1):
        ws_activos.cell(row=row_idx, column=valor_col).number_format = '$#,##0'
    _adjust_column_widths(ws_activos, headers)

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
