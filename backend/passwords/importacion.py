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


def _clave(titulo, usuario):
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
        _clave(t, u)
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
        clave = _clave(datos["titulo"], datos["usuario"])
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
