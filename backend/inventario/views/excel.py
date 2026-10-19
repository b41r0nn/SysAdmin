"""Exportación e importación de activos en Excel."""
from datetime import date, datetime


import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render

import openpyxl


from ..models import (
    Activo, TIPOS, ESTADOS,
)

from accounts.permisos import requiere_permiso
from core.utils import guardar_excel

logger = logging.getLogger(__name__)



# ══════════════════════════════════════════════════════════════════════════════
# Exportar inventario a Excel — selección de columnas
# ══════════════════════════════════════════════════════════════════════════════

@requiere_permiso("inventario", "lectura")
def exportar_opciones(request):
    secciones = [
        {
            "nombre": "Información general",
            "campos": [
                {"key": "id", "label": "ID"},
                {"key": "tipo", "label": "Tipo de dispositivo"},
                {"key": "marca", "label": "Marca"},
                {"key": "modelo", "label": "Modelo"},
                {"key": "serial", "label": "Serial"},
                {"key": "estado", "label": "Estado"},
                {"key": "ubicacion", "label": "Ubicación física"},
                {"key": "fecha_compra", "label": "Fecha de compra"},
                {"key": "proveedor", "label": "Proveedor"},
                {"key": "valor_compra", "label": "Valor de compra"},
                {"key": "observaciones", "label": "Observaciones"},
            ],
        },
        {
            "nombre": "Garantía",
            "campos": [
                {"key": "garantia_meses", "label": "Garantía fábrica (meses)"},
                {"key": "garantia_extendida", "label": "Garantía extendida"},
                {"key": "garantia_anos", "label": "Años garantía extendida"},
                {"key": "en_garantia", "label": "En garantía"},
                {"key": "fecha_vencimiento_garantia", "label": "Fecha vencimiento garantía"},
            ],
        },
        {
            "nombre": "Escritorio / Portátil",
            "campos": [
                {"key": "nombre_equipo", "label": "Nombre del equipo"},
                {"key": "disco_capacidad", "label": "Capacidad disco"},
                {"key": "tipo_disco", "label": "Tipo de disco"},
                {"key": "ram", "label": "RAM"},
                {"key": "procesador", "label": "Procesador"},
                {"key": "sistema_operativo", "label": "Sistema operativo"},
                {"key": "licencia_so", "label": "Licencia SO"},
                {"key": "usuario_red", "label": "Usuario de red"},
                {"key": "usuario_admin_local", "label": "Admin local"},
                {"key": "ip_equipo", "label": "IP del equipo"},
                {"key": "mac_equipo", "label": "MAC del equipo"},
            ],
        },
        {
            "nombre": "Celular",
            "campos": [
                {"key": "imei", "label": "IMEI"},
                {"key": "almacenamiento", "label": "Almacenamiento"},
                {"key": "ram_celular", "label": "RAM"},
                {"key": "procesador_celular", "label": "Procesador"},
                {"key": "tipo_disco_celular", "label": "Tipo de disco"},
                {"key": "cuenta_correo_dispositivo", "label": "Cuenta correo"},
                {"key": "numero_linea", "label": "Número de línea"},
                {"key": "operador", "label": "Operador"},
            ],
        },
        {
            "nombre": "Teléfono fijo",
            "campos": [
                {"key": "extension", "label": "Extensión"},
                {"key": "puerto_jack", "label": "Puerto / Jack"},
                {"key": "linea_asignada", "label": "Línea asignada"},
            ],
        },
        {
            "nombre": "Monitor",
            "campos": [
                {"key": "pulgadas", "label": "Pulgadas"},
                {"key": "resolucion", "label": "Resolución"},
                {"key": "tipo_panel", "label": "Tipo de panel"},
                {"key": "conectores", "label": "Conectores"},
            ],
        },
        {
            "nombre": "Asignación",
            "campos": [
                {"key": "asignado_a", "label": "Asignado a"},
                {"key": "documento_usuario", "label": "Documento usuario"},
                {"key": "area_usuario", "label": "Área usuario"},
                {"key": "fecha_asignacion", "label": "Fecha asignación"},
            ],
        },
        {
            "nombre": "Metadatos",
            "campos": [
                {"key": "fecha_creacion", "label": "Fecha creación"},
                {"key": "ultima_actualizacion", "label": "Última actualización"},
            ],
        },
    ]
    return render(request, "inventario/inventario_exportar_opciones.html", {"secciones": secciones})


# ── Importación masiva de Activos desde Excel ───────────────────────────────────

# Mapeo inverso: label del Excel -> (campo_modelo, transformador)
# Basado en CAMPOS_INVENTARIO de reports.datos (mismos labels)
LABEL_TO_CAMPO = {
    "ID": ("id", None),
    "Tipo de dispositivo": ("tipo_dispositivo", None),
    "Marca": ("marca", None),
    "Modelo": ("modelo", None),
    "Serial": ("serial", None),
    "Estado": ("estado", None),
    "Ubicación física": ("ubicacion_fisica", None),
    "Fecha de compra": ("fecha_compra", None),
    "Proveedor": ("proveedor", None),
    "Valor de compra": ("valor_compra", None),
    "Garantía fábrica (meses)": ("garantia_fabrica_meses", None),
    "Garantía extendida": ("garantia_extendida", None),
    "Años garantía extendida": ("anios_garantia_extendida", None),
    "En garantía": ("en_garantia", None),
    "Fecha vencimiento garantía": ("fecha_vencimiento_garantia", None),
    "Observaciones": ("observaciones", None),
    "Nombre del equipo": ("nombre_equipo", None),
    "Capacidad disco": ("disco_capacidad", None),
    "Tipo de disco": ("tipo_disco", None),
    "RAM": ("ram", None),
    "Procesador": ("procesador", None),
    "Sistema operativo": ("sistema_operativo", None),
    "Licencia SO": ("licencia_so", None),
    "Usuario de red": ("usuario_red", None),
    "Admin local": ("usuario_admin_local", None),
    "IP del equipo": ("ip_equipo", None),
    "MAC del equipo": ("mac_equipo", None),
    "IMEI": ("imei", None),
    "Almacenamiento": ("almacenamiento", None),
    "RAM (celular)": ("ram_celular", None),
    "Procesador (celular)": ("procesador_celular", None),
    "Tipo de disco (celular)": ("tipo_disco_celular", None),
    "Correo dispositivo": ("cuenta_correo_dispositivo", None),
    "Número de línea": ("numero_linea", None),
    "Operador": ("operador", None),
    "Extensión": ("extension", None),
    "Puerto / Jack": ("puerto_jack", None),
    "Línea asignada": ("linea_asignada", None),
    "Pulgadas": ("pulgadas", None),
    "Resolución": ("resolucion", None),
    "Tipo de panel": ("tipo_panel", None),
    "Conectores": ("conectores", None),
    "Asignado a": ("asignado_a", None),  # se ignora en import (FK)
    "Documento usuario": ("documento_usuario", None),  # se ignora
    "Área usuario": ("area_usuario", None),  # se ignora
    "Fecha asignación": ("fecha_asignacion", None),  # se ignora
    "Fecha creación": ("fecha_creacion", None),  # auto
    "Última actualización": ("fecha_actualizacion", None),  # auto
}

# Campos que se pueden importar directamente (no FK, no auto)
CAMPOS_IMPORTABLES = {
    k for k in LABEL_TO_CAMPO
    if LABEL_TO_CAMPO[k][0] not in ("asignado_a", "documento_usuario", "area_usuario", "fecha_asignacion", "fecha_creacion", "ultima_actualizacion")
}

# Valores válidos para choices (case-insensitive)
TIPOS_VALIDOS = {v.lower(): k for k, v in TIPOS}
ESTADOS_VALIDOS = {v.lower(): k for k, v in ESTADOS}


def _parse_valor_compra(valor):
    """Normaliza un valor monetario colombiano a float.

    Soporta:
    - 1.200.000,50  (punto miles, coma decimal)  -> 1200000.50
    - 1,200,000.50  (coma miles, punto decimal)  -> 1200000.50
    - 1200000,50    (sin separador de miles)     -> 1200000.50
    - 1200000.50    (sin separador de miles)     -> 1200000.50
    - $ 1.200.000   (con símbolo y espacios)     -> 1200000.0
    """
    if valor is None:
        return None
    s = str(valor).strip().replace("$", "").replace(" ", "")
    if not s:
        return None

    comas = s.count(",")
    puntos = s.count(".")

    if comas > 0:
        # Formato colombiano: coma es decimal, puntos son miles.
        s = s.replace(".", "").replace(",", ".")
    elif puntos > 1:
        # Múltiples puntos: separadores de miles.
        s = s.replace(".", "")
    elif puntos == 1:
        # Un solo punto: si la parte decimal tiene 1 o 2 dígitos es decimal,
        # si tiene 3 o más se asume separador de miles (formato colombiano).
        entera, decimal = s.split(".")
        if len(decimal) > 2:
            s = s.replace(".", "")

    try:
        return float(s)
    except ValueError:
        return None


def _normalizar_valor(label, valor):
    """Normaliza un valor según el tipo de campo."""
    if valor is None or str(valor).strip() == "":
        return ""
    valor = str(valor).strip()
    campo = LABEL_TO_CAMPO.get(label, ("", None))[0]
    if campo == "tipo_dispositivo":
        return TIPOS_VALIDOS.get(valor.lower(), valor)
    if campo == "estado":
        return ESTADOS_VALIDOS.get(valor.lower(), valor)
    if campo in ("garantia_extendida", "en_garantia"):
        return valor.lower() in ("sí", "si", "yes", "true", "1")
    if campo == "valor_compra":
        return _parse_valor_compra(valor)
    if campo in ("garantia_fabrica_meses", "anios_garantia_extendida"):
        try:
            return int(valor)
        except (ValueError, TypeError):
            return None
    if campo == "fecha_compra":
        # intenta varios formatos
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                dt = datetime.strptime(valor, fmt).date()
                return dt.isoformat()  # string ISO para guardar en sesión (JSON)
            except ValueError:
                continue
        return None
    if campo == "pulgadas":
        try:
            return float(valor.replace(",", "."))
        except (ValueError, TypeError):
            return None
    return valor


def _parsear_excel_activos(archivo):
    """Lee la primera hoja de un .xlsx y retorna (filas, advertencias)."""
    wb = openpyxl.load_workbook(archivo, read_only=True, data_only=True)
    ws = wb.worksheets[0]

    # Mapa de índices de columna -> campo_modelo según la fila de headers
    header_map = {}
    headers = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    for idx, header in enumerate(headers):
        if header in CAMPOS_IMPORTABLES:
            header_map[idx] = header

    advertencias = []
    if "Serial" not in header_map.values():
        advertencias.append('No se encontró la columna "Serial" — es obligatoria para importar.')

    filas = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        registro = {}
        for idx, label in header_map.items():
            valor = row[idx] if idx < len(row) else None
            if valor is None or str(valor).strip() == "":
                continue
            campo = LABEL_TO_CAMPO.get(label, ("", None))[0]
            if not campo:
                continue
            valor_norm = _normalizar_valor(label, valor)
            if valor_norm not in ("", None):
                registro[campo] = valor_norm

        # Ignorar filas totalmente vacías
        if not registro:
            continue

        serial = registro.get("serial", "")
        tipo = registro.get("tipo_dispositivo", "")
        if not serial:
            estado = "error_falta_serial"
        elif Activo.objects.filter(serial=serial).exists():
            estado = "duplicado"
        elif not tipo:
            estado = "error_falta_tipo"
        else:
            estado = "ok"

        # Para la vista previa mostramos los campos principales
        filas.append({
            "datos": registro,
            "estado": estado,
            "preview": {
                "tipo": tipo,
                "marca": registro.get("marca", ""),
                "modelo": registro.get("modelo", ""),
                "serial": serial,
            }
        })
    wb.close()
    return filas, advertencias


@requiere_permiso("inventario", "escritura")
def importar_activos(request):
    if request.method == "POST":
        archivo = request.FILES.get("archivo")
        if not archivo:
            messages.error(request, "Debes seleccionar un archivo .xlsx")
            return redirect("inventario:importar")
        if not archivo.name.lower().endswith(".xlsx"):
            messages.error(request, "El archivo debe ser .xlsx (Excel)")
            return redirect("inventario:importar")

        try:
            filas, advertencias = _parsear_excel_activos(archivo)
        except Exception:
            logger.exception("No se pudo leer el archivo .xlsx de activos")
            messages.error(request, "No se pudo leer el archivo. ¿Es un .xlsx válido?")
            return redirect("inventario:importar")

        request.session["importar_activos_filas"] = filas
        request.session["importar_activos_nombre"] = archivo.name
        if advertencias:
            for advertencia in advertencias:
                messages.warning(request, advertencia)

        resumen = {
            "ok": sum(1 for f in filas if f["estado"] == "ok"),
            "duplicados": sum(1 for f in filas if f["estado"] == "duplicado"),
            "errores": sum(1 for f in filas if f["estado"].startswith("error")),
            "total": len(filas),
        }
        return render(request, "inventario/importar_preview.html", {
            "filas": filas,
            "resumen": resumen,
            "nombre_archivo": archivo.name,
        })

    return render(request, "inventario/importar.html")


@requiere_permiso("inventario", "escritura")
def confirmar_importar_activos(request):
    if request.method != "POST":
        return redirect("inventario:importar")

    filas = request.session.pop("importar_activos_filas", None)
    request.session.pop("importar_activos_nombre", None)
    if filas is None:
        messages.error(request, "La vista previa expiró. Vuelve a subir el archivo.")
        return redirect("inventario:importar")

    creados = 0
    duplicados = 0
    errores = 0
    for fila in filas:
        if fila["estado"] != "ok":
            if fila["estado"] == "duplicado":
                duplicados += 1
            else:
                errores += 1
            continue
        datos = fila["datos"].copy()
        # Convertir fecha ISO string a date object
        fc = datos.get("fecha_compra")
        if isinstance(fc, str):
            try:
                datos["fecha_compra"] = date.fromisoformat(fc)
            except ValueError:
                datos.pop("fecha_compra", None)
        # Doble verificación contra duplicados
        if Activo.objects.filter(serial=datos.get("serial")).exists():
            duplicados += 1
            continue
        try:
            with transaction.atomic():
                Activo.objects.create(**datos)
            creados += 1
        except (IntegrityError, ValidationError, ValueError, TypeError) as exc:
            logger.warning("Importación: fila con error (%s): %s", datos.get("serial"), exc)
            errores += 1

    messages.success(
        request,
        f"Importación terminada: {creados} activos creados, "
        f"{duplicados} omitidos por duplicado, {errores} con error."
    )
    return redirect("inventario:lista")


@requiere_permiso("inventario", "lectura")
def descargar_plantilla_activos(request):
    """Descarga plantilla Excel con headers y fila de ejemplo."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Plantilla Activos"

    # Headers en el mismo orden que CAMPOS_IMPORTABLES (columnas principales primero)
    headers = [
        "Tipo de dispositivo",
        "Marca",
        "Modelo",
        "Serial",
        "Estado",
        "Ubicación física",
        "Fecha de compra",
        "Proveedor",
        "Valor de compra",
        "Garantía fábrica (meses)",
        "Garantía extendida",
        "Años garantía extendida",
        "Observaciones",
        "Nombre del equipo",
        "Capacidad disco",
        "Tipo de disco",
        "RAM",
        "Procesador",
        "Sistema operativo",
        "Licencia SO",
        "Usuario de red",
        "Admin local",
        "IP del equipo",
        "MAC del equipo",
        "IMEI",
        "Almacenamiento",
        "RAM (celular)",
        "Procesador (celular)",
        "Tipo de disco (celular)",
        "Correo dispositivo",
        "Número de línea",
        "Operador",
        "Extensión",
        "Puerto / Jack",
        "Línea asignada",
        "Pulgadas",
        "Resolución",
        "Tipo de panel",
        "Conectores",
    ]

    # Estilo header
    header_font = openpyxl.styles.Font(bold=True, color="FFFFFF")
    header_fill = openpyxl.styles.PatternFill(start_color="0156A6", end_color="0156A6", fill_type="solid")
    header_alignment = openpyxl.styles.Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = openpyxl.styles.Border(
        left=openpyxl.styles.Side(style="thin"),
        right=openpyxl.styles.Side(style="thin"),
        top=openpyxl.styles.Side(style="thin"),
        bottom=openpyxl.styles.Side(style="thin"),
    )

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    # Fila de ejemplo
    ejemplo = [
        "Portátil",                    # Tipo de dispositivo
        "Dell",                        # Marca
        "Latitude 3420",               # Modelo
        "SN123456",                    # Serial
        "Disponible",                  # Estado
        "Oficina 101",                 # Ubicación física
        "2024-03-15",                  # Fecha de compra (YYYY-MM-DD)
        "Dell Corp",                   # Proveedor
        "1200000",                     # Valor de compra
        "24",                          # Garantía fábrica (meses)
        "Sí",                          # Garantía extendida
        "2",                           # Años garantía extendida
        "Equipo nuevo para desarrollador",  # Observaciones
        "DESK-DEV-01",                 # Nombre del equipo
        "512GB SSD",                   # Capacidad disco
        "SSD",                         # Tipo de disco
        "16GB",                        # RAM
        "Intel Core i5-1335U",         # Procesador
        "Windows 11 Pro",              # Sistema operativo
        "OEM-12345",                   # Licencia SO
        "jperez",                      # Usuario de red
        "adminlocal",                  # Admin local
        "192.168.1.50",                # IP del equipo
        "00:1A:2B:3C:4D:5E",           # MAC del equipo
        "",                            # IMEI (solo celular)
        "",                            # Almacenamiento (solo celular)
        "",                            # RAM (celular)
        "",                            # Procesador (celular)
        "",                            # Tipo de disco (celular)
        "",                            # Correo dispositivo (solo celular)
        "",                            # Número de línea (solo celular)
        "",                            # Operador (solo celular)
        "",                            # Extensión (solo teléfono fijo)
        "",                            # Puerto / Jack (solo teléfono fijo)
        "",                            # Línea asignada (solo teléfono fijo)
        "",                            # Pulgadas (solo monitor)
        "",                            # Resolución (solo monitor)
        "",                            # Tipo de panel (solo monitor)
        "",                            # Conectores (solo monitor)
    ]

    for col_idx, valor in enumerate(ejemplo, 1):
        cell = ws.cell(row=2, column=col_idx, value=valor)
        cell.border = thin_border
        cell.alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="top")

    # Segunda fila de ejemplo (celular)
    ejemplo2 = [
        "Celular",
        "Samsung",
        "Galaxy S23",
        "IMEI123456789012345",
        "Asignado",
        "Bodega Central",
        "2024-01-10",
        "Samsung Colombia",
        "800000",
        "12",
        "No",
        "",
        "Entrega a gerente",
        "", "", "", "", "", "", "", "", "", "",
        "123456789012345",
        "256GB",
        "8GB",
        "Snapdragon 8 Gen 2",
        "UFS 4.0",
        "gerente@empresa.com",
        "3001234567",
        "Claro",
        "", "", "", "", "", "", "", "",
    ]

    for col_idx, valor in enumerate(ejemplo2, 1):
        cell = ws.cell(row=3, column=col_idx, value=valor)
        cell.border = thin_border
        cell.alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="top")

    # Ajustar anchos de columna
    for col_idx in range(1, len(headers) + 1):
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 22

    # Hoja de instrucciones
    ws_inst = wb.create_sheet("Instrucciones")
    instrucciones = [
        ["INSTRUCCIONES DE USO"],
        [""],
        ["1. Complete la hoja 'Plantilla Activos' copiando y pegando sus datos."],
        ["2. No elimine ni reordene las columnas; solo agregue filas debajo de los ejemplos."],
        ["3. El archivo debe guardarse como .xlsx (Excel 2007+)"],
        [""],
        ["CAMPOS OBLIGATORIOS:"],
        ["  - Serial: único, máximo 150 caracteres (clave para evitar duplicados)"],
        ["  - Tipo de dispositivo: exactamente uno de:"],
        ["      Celular, Equipo Escritorio, Portátil, Teléfono Fijo, Monitor"],
        ["  - Estado: exactamente uno de:"],
        ["      Disponible, Asignado, En mantenimiento, En reparación, Dado de baja"],
        [""],
        ["CAMPOS POR TIPO DE DISPOSITIVO (los demás déjelos vacíos):"],
        ["  - Portátil / Equipo Escritorio: Nombre del equipo, Capacidad disco, Tipo de disco,"],
        ["      RAM, Procesador, Sistema operativo, Licencia SO, Usuario de red,"],
        ["      Admin local, IP del equipo, MAC del equipo"],
        ["  - Celular: IMEI, Almacenamiento, RAM (celular), Procesador (celular),"],
        ["      Tipo de disco (celular), Correo dispositivo, Número de línea, Operador"],
        ["  - Teléfono Fijo: Extensión, Puerto / Jack, Línea asignada"],
        ["  - Monitor: Pulgadas, Resolución, Tipo de panel, Conectores"],
        [""],
        ["FORMATOS:"],
        ["  - Fecha de compra: YYYY-MM-DD (ej. 2024-03-15)"],
        ["  - Valor de compra: número entero o con punto decimal (ej. 1200000 o 1200000.50)"],
        ["  - Garantía extendida: Sí / No"],
        ["  - Valor de compra y Garantía fábrica: solo números"],
        ["  - IMEI: 15 dígitos sin espacios ni guiones"],
        ["  - MAC: formato XX:XX:XX:XX:XX:XX"],
        ["  - IP: formato IPv4 (ej. 192.168.1.50)"],
        ["  - Pulgadas: número decimal con punto (ej. 23.8)"],
        [""],
        ["IMPORTANTE:"],
        ["  - El Serial es único. Si ya existe en el sistema, la fila se omitirá."],
        ["  - Las filas sin Serial o sin Tipo de dispositivo se marcarán como error."],
        ["  - Los campos no listados arriba se ignoran (puede borrar columnas extra)."],
        ["  - No modifique los encabezados; el sistema los lee por nombre exacto."],
    ]

    for row_idx, line in enumerate(instrucciones, 1):
        cell = ws_inst.cell(row=row_idx, column=1, value=line[0])
        if row_idx == 1:
            cell.font = openpyxl.styles.Font(bold=True, size=14, color="0156A6")
        cell.alignment = openpyxl.styles.Alignment(wrap_text=True)

    ws_inst.column_dimensions["A"].width = 100

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="plantilla_importar_activos.xlsx"'
    guardar_excel(wb, response)
    return response
