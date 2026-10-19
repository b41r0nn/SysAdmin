"""Paleta corporativa y helpers de estilo para los Excel REDIHOS."""
import os

from django.conf import settings
from django.utils import timezone
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.units import pixels_to_EMU
from PIL import Image as PILImage




# ── Paleta corporativa REDIHOS ───────────────────────────────────────────────
AZUL = "0156A6"
AZUL_OSCURO = "013D7A"
AZUL_CLARO = "E6F0FA"
NARANJA = "F18020"
GRIS_TXT = "1F2937"
BLANCO = "FFFFFF"

LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "img", "logo_redihos_mark.png")


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
