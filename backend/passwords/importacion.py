"""Importación masiva de credenciales desde Excel.

Cada contraseña se cifra en cuanto se lee: la vista previa y la sesión (que
vive en la base de datos) solo guardan el texto cifrado, nunca la clave.
"""
import unicodedata
from datetime import date, datetime

import openpyxl
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from .crypto import build_fernet
from .models import Credencial

MAX_FILAS = 1000
MAX_BYTES = 5 * 1024 * 1024

ALIAS = {
    "titulo": {"titulo", "nombre", "servicio", "sistema", "aplicacion"},
    "usuario": {"usuario", "user", "login", "cuenta", "correo", "email"},
    "secreto": {"contrasena", "clave", "password", "pass"},
    "url": {"url", "sitio", "sitio web", "enlace", "link", "direccion", "ip"},
    "notas": {"notas", "nota", "observaciones", "comentarios", "descripcion"},
    "estado": {"estado"},
    "fecha_expiracion": {
        "fecha de expiracion", "expiracion", "vence", "vencimiento", "fecha de vencimiento",
    },
}
ESTADOS = {"activa", "expirada", "revocada"}
FORMATOS_FECHA = ("%d/%m/%Y", "%Y-%m-%d")
COLUMNAS_OBLIGATORIAS = (("titulo", "Título"), ("secreto", "Contraseña"))


class ArchivoInvalido(Exception):
    """El archivo no se puede importar; el texto es el mensaje para el usuario."""


def _sin_tildes(texto):
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _normalizar_encabezado(valor):
    texto = _sin_tildes(str(valor or "")).lower().replace("*", " ")
    return " ".join(texto.split())


def _campo_de(encabezado):
    normalizado = _normalizar_encabezado(encabezado)
    for campo, alias in ALIAS.items():
        if normalizado in alias:
            return campo
    return None


def _texto(valor):
    """Valor de celda como texto. Las fechas se tratan aparte."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        return str(int(valor)) if valor.is_integer() else str(valor)
    return str(valor)


def _normalizar_url(texto):
    """Devuelve (url, nota). Lo que no sea una URL válida pasa a las notas."""
    if not texto:
        return "", ""
    url = texto if "://" in texto else f"https://{texto}"
    if len(url) > 200:
        return "", f"Sitio: {texto}"
    try:
        URLValidator()(url)
    except ValidationError:
        return "", f"Sitio: {texto}"
    return url, ""


def _fecha(valor):
    """Devuelve (iso | None, error)."""
    if valor in (None, ""):
        return None, ""
    if isinstance(valor, datetime):
        return valor.date().isoformat(), ""
    if isinstance(valor, date):
        return valor.isoformat(), ""
    texto = _texto(valor).strip()
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato).date().isoformat(), ""
        except ValueError:
            continue
    return None, f"Fecha de expiración no válida: «{texto}»"


def clave_duplicado(titulo, usuario):
    return (titulo.strip().lower(), usuario.strip().lower())


def _validar(datos, valor_secreto, estado_crudo, fecha_cruda):
    """Devuelve el motivo del error o "" si la fila es válida."""
    if not datos["titulo"]:
        return "Falta el título"
    if isinstance(valor_secreto, (date, datetime)):
        return "Excel convirtió la contraseña en fecha; usa la plantilla (columnas en Texto)"
    if not datos["secreto"].strip():
        return "Falta la contraseña"
    if len(datos["titulo"]) > 150:
        return "El título supera 150 caracteres"
    if len(datos["usuario"]) > 150:
        return "El usuario supera 150 caracteres"
    estado = _sin_tildes(estado_crudo).lower()
    if estado and estado not in ESTADOS:
        return f"Estado no válido: «{estado_crudo}». Usa Activa, Expirada o Revocada"
    _, error_fecha = _fecha(fecha_cruda)
    return error_fecha


def leer_credenciales(archivo, vault):
    """Lee la primera hoja del Excel y valida cada fila contra la bóveda.

    Returns:
        (filas, advertencias). Cada fila es un dict serializable a JSON con
        fila, titulo, usuario, url, notas, estado, fecha_expiracion,
        secreto_cifrado, resultado ("nueva" | "ya_existe" | "repetida" |
        "error") y detalle.
    """
    wb = openpyxl.load_workbook(archivo, data_only=True)
    try:
        ws = wb.worksheets[0]
        encabezados = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        columnas = {}
        for indice, encabezado in enumerate(encabezados):
            campo = _campo_de(encabezado)
            if campo and campo not in columnas:
                columnas[campo] = indice

        advertencias = []
        faltantes = []
        for campo, nombre in COLUMNAS_OBLIGATORIAS:
            if campo not in columnas:
                advertencias.append(f'No se encontró la columna "{nombre}".')
                faltantes.append(nombre)

        crudas = []
        for numero, fila in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if all(_texto(v).strip() == "" for v in fila):
                continue
            crudas.append((numero, fila))
            if len(crudas) > MAX_FILAS:
                raise ArchivoInvalido(f"El archivo tiene más de {MAX_FILAS} filas con datos.")
    finally:
        wb.close()

    existentes = {
        clave_duplicado(t, u)
        for t, u in Credencial.objects.filter(vault=vault).values_list("titulo", "usuario")
    }
    vistas = set()
    fernet = build_fernet()
    filas = []
    for numero, fila in crudas:
        def celda(campo, fila=fila):
            indice = columnas.get(campo)
            return fila[indice] if indice is not None and indice < len(fila) else None

        valor_secreto = celda("secreto")
        datos = {
            "titulo": _texto(celda("titulo")).strip(),
            "usuario": _texto(celda("usuario")).strip(),
            "secreto": "" if isinstance(valor_secreto, (date, datetime)) else _texto(valor_secreto),
        }
        estado_crudo = _texto(celda("estado")).strip()
        fecha_cruda = celda("fecha_expiracion")
        url, nota_url = _normalizar_url(_texto(celda("url")).strip())
        notas = "\n".join(t for t in (_texto(celda("notas")).strip(), nota_url) if t)
        fecha_iso, _ = _fecha(fecha_cruda)

        registro = {
            "fila": numero,
            "titulo": datos["titulo"],
            "usuario": datos["usuario"],
            "url": url,
            "notas": notas,
            "estado": _sin_tildes(estado_crudo).lower() or "activa",
            "fecha_expiracion": fecha_iso,
            "secreto_cifrado": "",
            "resultado": "nueva",
            "detalle": "",
        }

        if faltantes:
            error = "Falta la columna " + " y ".join(f'"{n}"' for n in faltantes)
        else:
            error = _validar(datos, valor_secreto, estado_crudo, fecha_cruda)
        clave = clave_duplicado(datos["titulo"], datos["usuario"])
        if error:
            registro.update(resultado="error", detalle=error)
        elif clave in existentes:
            registro.update(resultado="ya_existe", detalle="Ya existe: mismo título y usuario")
        elif clave in vistas:
            registro.update(resultado="repetida", detalle="Repetida en el archivo")
        else:
            vistas.add(clave)
            registro["secreto_cifrado"] = fernet.encrypt(datos["secreto"].encode("utf-8")).decode("utf-8")
        filas.append(registro)

    return filas, advertencias


def resumen(filas):
    return {
        "nuevas": sum(1 for f in filas if f["resultado"] == "nueva"),
        "ya_existen": sum(1 for f in filas if f["resultado"] in ("ya_existe", "repetida")),
        "errores": sum(1 for f in filas if f["resultado"] == "error"),
        "total": len(filas),
    }


ENCABEZADOS_PLANTILLA = ["Título", "Usuario", "Contraseña", "URL", "Notas", "Estado", "Fecha de expiración"]
EJEMPLOS_PLANTILLA = [
    ["Correo Gerencia", "gerencia@empresa.com", "Ejemplo-Clave-1", "https://outlook.office.com",
     "Cuenta principal", "Activa", ""],
    ["Router oficina", "admin", "Ejemplo-Clave-2", "http://192.168.1.1", "", "Activa", "31/12/2027"],
]
INSTRUCCIONES_PLANTILLA = [
    "INSTRUCCIONES DE USO",
    "",
    "1. Pegue sus contraseñas en la hoja 'Plantilla Contraseñas', debajo de los encabezados.",
    "   Borre o reemplace las dos filas de ejemplo antes de subir el archivo.",
    "2. Todas las columnas están en formato Texto para que Excel no cambie claves como 00123 o 1/2/24.",
    "   Si pega desde otro Excel, use 'Pegar valores'.",
    "3. Guarde como .xlsx y súbalo desde la bóveda: Importar desde Excel.",
    "",
    "COLUMNAS OBLIGATORIAS: Título y Contraseña.",
    "COLUMNAS OPCIONALES: Usuario, URL, Notas, Estado, Fecha de expiración.",
    "  - Estado: Activa, Expirada o Revocada (vacío = Activa).",
    "  - Fecha de expiración: dd/mm/aaaa (ej. 31/12/2027) o aaaa-mm-dd.",
    "  - URL: si no empieza por http(s):// se le agrega https://; si no es una dirección válida, va a Notas.",
    "",
    "IMPORTANTE:",
    "  - Si en la bóveda ya existe una credencial con el mismo Título y Usuario, la fila se omite (no se sobrescribe).",
    f"  - Máximo {MAX_FILAS} filas por archivo.",
    "  - Nada se guarda hasta que confirme en la vista previa.",
    "  - Cuando termine, borre este archivo de su PC y de la papelera: tiene las contraseñas en texto plano.",
]


def plantilla_workbook():
    """Plantilla Excel para importar credenciales (columnas en formato Texto)."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Plantilla Contraseñas"
    borde = Border(*(Side(style="thin") for _ in range(4)))

    for fila in range(1, MAX_FILAS + 2):
        for columna in range(1, len(ENCABEZADOS_PLANTILLA) + 1):
            ws.cell(row=fila, column=columna).number_format = "@"

    for columna, texto in enumerate(ENCABEZADOS_PLANTILLA, 1):
        celda = ws.cell(row=1, column=columna, value=texto)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill(start_color="0156A6", end_color="0156A6", fill_type="solid")
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        celda.border = borde
        ws.column_dimensions[openpyxl.utils.get_column_letter(columna)].width = 26

    for fila, ejemplo in enumerate(EJEMPLOS_PLANTILLA, 2):
        for columna, valor in enumerate(ejemplo, 1):
            celda = ws.cell(row=fila, column=columna, value=valor or None)
            celda.border = borde

    hoja = wb.create_sheet("Instrucciones")
    for fila, linea in enumerate(INSTRUCCIONES_PLANTILLA, 1):
        celda = hoja.cell(row=fila, column=1, value=linea)
        if fila == 1:
            celda.font = Font(bold=True, size=14, color="0156A6")
    hoja.column_dimensions["A"].width = 110
    return wb
