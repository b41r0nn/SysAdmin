"""Importación masiva de credenciales desde Excel.

Cada contraseña se cifra en cuanto se lee: la vista previa y la sesión (que
vive en la base de datos) solo guardan el texto cifrado, nunca la clave.
"""
import re
import unicodedata
from datetime import date, datetime, time, timedelta

import openpyxl
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from .crypto import build_fernet
from .models import Credencial

MAX_FILAS = 1000
MAX_BYTES = 5 * 1024 * 1024
# Solo se miran las primeras columnas del encabezado: una celda con formato en
# XFD1 haría que el rango "usado" de la hoja tenga 16.384 columnas.
MAX_COLUMNAS = 50

ALIAS = {
    "titulo": {"titulo", "nombre", "servicio", "sistema", "aplicacion", "plataforma"},
    "usuario": {
        "usuario", "user", "username", "login", "cuenta", "correo", "email", "e mail", "mail",
        "correo electronico", "usuario correo", "nombre de usuario",
    },
    "secreto": {
        "contrasena", "contrasenas", "clave", "claves", "password", "passwords", "pass", "clave de acceso",
    },
    "url": {
        "url", "sitio", "sitio web", "enlace", "link", "direccion", "ip", "direccion ip",
        "pagina", "pagina web", "web", "host", "servidor",
    },
    "notas": {
        "notas", "nota", "observaciones", "observacion", "comentarios", "comentario", "descripcion", "detalle",
    },
    "estado": {"estado"},
    "fecha_expiracion": {
        "fecha de expiracion", "expiracion", "vence", "vencimiento", "fecha de vencimiento",
        "caduca", "caducidad",
    },
}
ESTADOS = {"activa", "expirada", "revocada"}
FORMATOS_FECHA = ("%d/%m/%Y", "%Y-%m-%d")
COLUMNAS_OBLIGATORIAS = (("titulo", "Título"), ("secreto", "Contraseña"))
# Formatos de número con los que Excel guarda lo mismo que se escribió.
FORMATOS_NUMERO_SEGUROS = {"General", "0", "@"}
# Un número de Excel (double) pierde dígitos a partir de ~15 cifras.
LIMITE_DIGITOS = 10 ** 15
# Solo se antepone https:// a algo con forma de host[:puerto][/ruta].
FORMA_DE_HOST = re.compile(r"[\w.-]+(:\d+)?(/\S*)?")
PARECE_DIRECCION = re.compile(r"^(https?://|www\.|\\\\)|^\d{1,3}(\.\d{1,3}){3}(:\d+)?(/\S*)?$", re.IGNORECASE)
# Las URL que no lo son solo hacen sospechar columnas cruzadas con varias filas.
MIN_FILAS_ORDEN = 3

ENCABEZADOS_PLANTILLA = ["Título", "Usuario", "Contraseña", "URL", "Notas", "Estado", "Fecha de expiración"]
EJEMPLOS_PLANTILLA = [
    ["Correo Gerencia", "gerencia@empresa.com", "Ejemplo-Clave-1", "https://outlook.office.com",
     "Cuenta principal", "Activa", ""],
    ["Router oficina", "admin", "Ejemplo-Clave-2", "http://192.168.1.1", "", "Activa", "31/12/2027"],
]
CLAVES_EJEMPLO = {ejemplo[2] for ejemplo in EJEMPLOS_PLANTILLA}
INSTRUCCIONES_PLANTILLA = [
    "INSTRUCCIONES DE USO",
    "",
    "1. Pegue sus contraseñas en la hoja 'Plantilla Contraseñas', debajo de los encabezados.",
    "   Borre o reemplace las dos filas de ejemplo: si las deja, se marcan con error y no se importan.",
    "2. Todas las columnas están en formato Texto para que Excel no cambie claves como 00123 o 1/2/24.",
    "   Si pega desde otro Excel, use Pegado especial > Texto (o 'Mantener solo texto') para que se copie",
    "   lo que se ve. Evite 'Pegar valores' si alguna clave parece fecha, hora o porcentaje.",
    "3. Guarde como .xlsx y súbalo desde la bóveda: Importar desde Excel.",
    "",
    "COLUMNAS OBLIGATORIAS: Título y Contraseña.",
    "COLUMNAS OPCIONALES: Usuario, URL, Notas, Estado, Fecha de expiración.",
    "  - También se reconocen: Nombre o Servicio (Título); Correo, E-mail o Login (Usuario);",
    "    Clave o Password (Contraseña); Sitio, Página web o Dirección IP (URL); Observaciones (Notas).",
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


class ArchivoInvalido(Exception):
    """El archivo no se puede importar; el texto es el mensaje para el usuario."""


def _sin_tildes(texto):
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _normalizar_encabezado(valor):
    texto = _sin_tildes(str(valor or "")).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texto).split())


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


def _error_de_la_clave(valor, tipo, formato):
    """Motivo por el que Excel pudo alterar la contraseña, o ""."""
    if isinstance(valor, bool) or tipo == "b":
        return "Excel convirtió la contraseña en VERDADERO/FALSO; escríbela como texto"
    if tipo == "e":
        return "La celda de la contraseña tiene un error de Excel (#N/A, #REF!…)"
    if isinstance(valor, (datetime, date, time, timedelta)):
        return "Excel convirtió la contraseña en fecha u hora; usa la plantilla (columnas en Texto)"
    if isinstance(valor, (int, float)):
        if abs(valor) >= LIMITE_DIGITOS:
            return "Número demasiado largo: Excel perdió dígitos; escribe la contraseña como texto"
        if (formato or "General") not in FORMATOS_NUMERO_SEGUROS:
            return ("Excel le dio formato de número (porcentaje, moneda o fecha) a la contraseña; "
                    "escríbela como texto")
    return ""


def _normalizar_url(texto):
    """Devuelve (url, nota). Lo que no sea una URL válida pasa a las notas."""
    if not texto:
        return "", ""
    if "://" in texto:
        url = texto
    elif FORMA_DE_HOST.fullmatch(texto):
        url = f"https://{texto}"
    else:
        return "", f"Sitio: {texto}"
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


def _validar(datos, error_clave, estado_crudo, fecha_cruda):
    """Devuelve el motivo del error o "" si la fila es válida."""
    if not datos["titulo"]:
        return "Falta el título"
    if error_clave:
        return error_clave
    if not datos["secreto"].strip():
        return "Falta la contraseña"
    if datos["secreto"] in CLAVES_EJEMPLO:
        return "Fila de ejemplo de la plantilla: bórrala o reemplázala"
    if len(datos["titulo"]) > 150:
        return "El título supera 150 caracteres"
    if len(datos["usuario"]) > 150:
        return "El usuario supera 150 caracteres"
    estado = _sin_tildes(estado_crudo).lower()
    if estado and estado not in ESTADOS:
        return f"Estado no válido: «{estado_crudo}». Usa Activa, Expirada o Revocada"
    _, error_fecha = _fecha(fecha_cruda)
    return error_fecha


def _leer_hoja(archivo):
    """Devuelve (columnas, ignoradas, filas) de la primera hoja.

    columnas: campo → índice; ignoradas: encabezados no reconocidos o repetidos;
    filas: [(número de fila en Excel, celdas)] sin las filas vacías.
    """
    wb = openpyxl.load_workbook(archivo, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        # Sin esto openpyxl confía en la dimensión que declara el archivo, que
        # una sola celda con formato lejos de los datos vuelve gigantesca.
        ws.reset_dimensions()
        encabezado = next(ws.iter_rows(min_row=1, max_row=1, max_col=MAX_COLUMNAS, values_only=True), ())
        columnas, ignoradas = {}, []
        for indice, valor in enumerate(encabezado):
            if valor is None or str(valor).strip() == "":
                continue
            campo = _campo_de(valor)
            if campo and campo not in columnas:
                columnas[campo] = indice
            else:
                ignoradas.append(str(valor).strip())

        ancho = max(columnas.values(), default=0) + 1
        filas = []
        for celdas in ws.iter_rows(min_row=2, max_col=ancho):
            if all(_texto(getattr(c, "value", None)).strip() == "" for c in celdas):
                continue
            numero = next(c.row for c in celdas if getattr(c, "row", None))
            filas.append((numero, celdas))
            if len(filas) > MAX_FILAS:
                raise ArchivoInvalido(f"El archivo tiene más de {MAX_FILAS} filas con datos.")
        return columnas, ignoradas, filas
    finally:
        wb.close()


def _advertencias(columnas, ignoradas):
    advertencias = []
    faltantes = [nombre for campo, nombre in COLUMNAS_OBLIGATORIAS if campo not in columnas]
    for nombre in faltantes:
        advertencias.append(f'No se encontró la columna "{nombre}".')
    if not faltantes and "usuario" not in columnas:
        advertencias.append(
            'No se encontró la columna "Usuario": las filas con el mismo título se tratarán como repetidas.'
        )
    if ignoradas:
        nombres = ", ".join(f"«{n}»" for n in ignoradas)
        advertencias.append(
            f"Se ignoraron columnas que no se reconocen o están repetidas: {nombres}. "
            "Si tienen datos que necesitas, renombra el encabezado (ver la hoja Instrucciones)."
        )
    return advertencias, faltantes


def leer_credenciales(archivo, vault):
    """Lee la primera hoja del Excel y valida cada fila contra la bóveda.

    Returns:
        (filas, advertencias). Cada fila es un dict serializable a JSON con
        fila, titulo, usuario, url, url_a_notas, notas, estado,
        fecha_expiracion, secreto_cifrado, resultado ("nueva" | "ya_existe" |
        "repetida" | "error") y detalle.
    """
    columnas, ignoradas, crudas = _leer_hoja(archivo)
    advertencias, faltantes = _advertencias(columnas, ignoradas)

    existentes = {
        clave_duplicado(t, u)
        for t, u in Credencial.objects.filter(vault=vault).values_list("titulo", "usuario")
    }
    vistas = set()
    fernet = build_fernet()
    filas = []
    con_clave = claves_como_direccion = urls_escritas = urls_a_notas = 0
    for numero, celdas in crudas:
        def celda(campo, celdas=celdas):
            indice = columnas.get(campo)
            return celdas[indice] if indice is not None and indice < len(celdas) else None

        def valor(campo):
            return getattr(celda(campo), "value", None)

        celda_clave = celda("secreto")
        valor_clave = getattr(celda_clave, "value", None)
        error_clave = ""
        if valor_clave is not None:
            error_clave = _error_de_la_clave(
                valor_clave,
                getattr(celda_clave, "data_type", None),
                getattr(celda_clave, "number_format", "General"),
            )
        datos = {
            "titulo": _texto(valor("titulo")).strip(),
            "usuario": _texto(valor("usuario")).strip(),
            "secreto": "" if error_clave else _texto(valor_clave),
        }
        estado_crudo = _texto(valor("estado")).strip()
        fecha_cruda = valor("fecha_expiracion")
        url_original = _texto(valor("url")).strip()
        url, nota_url = _normalizar_url(url_original)
        notas = "\n".join(t for t in (_texto(valor("notas")).strip(), nota_url) if t)
        fecha_iso, _ = _fecha(fecha_cruda)

        if datos["secreto"].strip():
            con_clave += 1
            claves_como_direccion += bool(PARECE_DIRECCION.match(datos["secreto"].strip()))
        if url_original:
            urls_escritas += 1
            urls_a_notas += bool(nota_url)

        registro = {
            "fila": numero,
            "titulo": datos["titulo"],
            "usuario": datos["usuario"],
            "url": url,
            "url_a_notas": bool(nota_url),
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
            error = _validar(datos, error_clave, estado_crudo, fecha_cruda)
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
            if isinstance(valor_clave, (int, float)):
                registro["detalle"] = "Revisa: en Excel era un número"
        filas.append(registro)

    # Columnas pegadas en otro orden: las claves terminarían en URL o en Notas,
    # en texto plano. Ante la sospecha no se importa nada.
    cruzadas = (claves_como_direccion and claves_como_direccion * 2 >= con_clave) or (
        urls_escritas >= MIN_FILAS_ORDEN and urls_a_notas * 2 >= urls_escritas
    )
    if cruzadas:
        advertencias.append(
            "Las contraseñas parecen direcciones o las URL no lo son: ¿pegaste las columnas en otro orden? "
            "Revisa el archivo; no se importó nada."
        )
        for registro in filas:
            registro.update(resultado="error", detalle="Revisa el orden de las columnas",
                            secreto_cifrado="", url="", url_a_notas=False, notas="")

    return filas, advertencias


def resumen(filas):
    return {
        "nuevas": sum(1 for f in filas if f["resultado"] == "nueva"),
        "ya_existen": sum(1 for f in filas if f["resultado"] in ("ya_existe", "repetida")),
        "errores": sum(1 for f in filas if f["resultado"] == "error"),
        "total": len(filas),
    }


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
