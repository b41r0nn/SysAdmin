"""Acta de mantenimiento en una sola hoja carta (§B7 del diseño).

Se arma siempre desde ``OrdenMantenimiento.datos_acta``, la foto congelada al
cerrar, más lo que ya es de la orden (checklist, fotos, repuestos, textos). Si
el contenido no cabe en una hoja, se prueba con letra más pequeña (``escala``).
"""

import logging

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse

from administracion.models import ConfiguracionSistema
from inventario.views.qr import _qr_data_uri

from . import services
from .models import FORMATO_ACTUAL, MAX_FOTOS_ACTA

logger = logging.getLogger(__name__)

PLANTILLA = "mantenimiento/acta_pdf.html"
# Escalas de la letra y las fotos, de la MAS GRANDE a la mas chica (ver la
# plantilla). Gana la primera que entre en una hoja: un acta corta aprovecha la
# hoja y una larga se achica. La 3 es la letra que usaba el acta antes (8,5 pt).
ESCALAS = (0, 1, 2, 3, 4, 5, 6)
ESCALA_BASE = 3
# Debajo de este sobrante no vale la pena re-renderizar para estirar el cuadro.
SOBRA_MINIMA_MM = 4
# Colchon al estirar, para no empujar las firmas a una segunda hoja.
COLCHON_MM = 3
# Aire entre el final del contenido y las firmas, ya con la reserva ajustada.
AIRE_RESERVA_MM = 2
MM_POR_PX = 25.4 / 96
PARES_POR_FILA = 3
VACIO = "—"


def url_hoja_de_vida(request, activo):
    """URL absoluta de la hoja de vida del equipo, la que abre el QR del acta."""
    path = reverse("mantenimiento:hoja_de_vida", args=[activo.pk])
    base = (settings.QR_BASE_URL or "").strip()
    if base:
        return f"{base.rstrip('/')}{path}"
    return request.build_absolute_uri(path)


def url_absoluta(path):
    """``path`` con el prefijo de ``QR_BASE_URL`` (sin petición, para los PDF); sin prefijo, el mismo ``path``."""
    base = (settings.QR_BASE_URL or "").strip()
    return f"{base.rstrip('/')}{path}" if base else path


def fotos_acta(orden):
    """Las fotos marcadas para el acta o, si no hay ninguna, las primeras. Máximo 3."""
    fotos = orden.fotos.order_by("fecha_creacion", "pk")
    marcadas = list(fotos.filter(en_acta=True)[:MAX_FOTOS_ACTA])
    return marcadas or list(fotos[:MAX_FOTOS_ACTA])


def columnas_checklist(items):
    """Reparte los puntos en dos columnas por sección, sin partir una sección.

    Cada grupo pesa sus puntos más uno (la fila del título). Van a la izquierda
    mientras lo acumulado ahí sea menos de la mitad del total. Además deja en
    cada punto ``numero``, su número en el acta.
    """
    grupos = []
    por_seccion = {}
    for item in items:
        grupo = por_seccion.get(item.seccion)
        if grupo is None:
            grupo = por_seccion[item.seccion] = {"seccion": item.seccion, "items": []}
            grupos.append(grupo)
        grupo["items"].append(item)

    total = sum(len(g["items"]) + 1 for g in grupos)
    izquierda, derecha = [], []
    peso = 0
    for grupo in grupos:
        if peso < total / 2:
            izquierda.append(grupo)
            peso += len(grupo["items"]) + 1
        else:
            derecha.append(grupo)

    numero = 0
    for grupo in izquierda + derecha:
        for item in grupo["items"]:
            numero += 1
            item.numero = numero
    return izquierda, derecha


def fallas_acta(orden):
    """Una línea por punto del checklist que falló: "descripción (falla): observación"."""
    return [
        f"{item.descripcion} (falla): {item.observacion}"
        for item in orden.checklist_items.all()
        if item.resultado == "falla"
    ]


def observaciones_acta(orden):
    """Líneas del cuadro de observaciones: las fallas del checklist y después las generales."""
    lineas = fallas_acta(orden)
    if orden.observaciones.strip():
        lineas.append(orden.observaciones.strip())
    return lineas


def resumen_checklist(items):
    resultados = [item.resultado for item in items]
    return {
        "total": len(resultados),
        "bien": resultados.count("bien"),
        "falla": resultados.count("falla"),
        "na": resultados.count("na"),
    }


def detalle_formato_nuevo(orden):
    """Resumen del checklist y fallas de una orden del formato nuevo; ``None`` si es del anterior.

    ``acta`` es verdadero solo cuando la vista del acta la serviría (cerrada y con datos congelados).
    """
    if orden.formato != FORMATO_ACTUAL:
        return None
    return {
        "resumen": resumen_checklist(list(orden.checklist_items.all())),
        "fallas": fallas_acta(orden),
        "acta": orden.estado == "cerrada" and bool(orden.datos_acta),
    }


def filas_equipo(datos, es_correctivo):
    """Los campos del equipo más Garantía y Próximo, en filas de 3 pares.

    El último valor de una fila incompleta ocupa las columnas que sobran.
    "Próximo" solo va en los preventivos.
    """
    pares = [*datos.get("campos", []), ["Garantía", datos.get("garantia") or VACIO]]
    if not es_correctivo:
        pares.append(["Próximo", datos.get("proximo") or VACIO])
    filas = []
    for inicio in range(0, len(pares), PARES_POR_FILA):
        fila = [{"etiqueta": e, "valor": v, "colspan": 1} for e, v in pares[inicio:inicio + PARES_POR_FILA]]
        fila[-1]["colspan"] = 1 + 2 * (PARES_POR_FILA - len(fila))
        filas.append(fila)
    return filas


def contexto_acta(orden, request, escala: int = ESCALA_BASE, alto_obs_mm=None, alto_reserva_mm=None):
    items = list(orden.checklist_items.all())
    datos = orden.datos_acta
    es_correctivo = orden.tipo == "correctivo"
    return {
        "orden": orden,
        "datos": datos,
        "config": ConfiguracionSistema.get_config(),
        "logo_path": services.LOGO_PATH,
        "qr": _qr_data_uri(url_hoja_de_vida(request, orden.activo)),
        "numero": f"{orden.pk:04d}",
        "es_correctivo": es_correctivo,
        "filas": filas_equipo(datos, es_correctivo),
        "columnas": columnas_checklist(items),
        "resumen": resumen_checklist(items),
        "fotos": [{"path": f.foto.path, "descripcion": f.descripcion} for f in fotos_acta(orden)],
        "repuestos": [f"{r.nombre} × {r.cantidad}" for r in orden.repuestos.order_by("nombre", "pk")],
        "observaciones": observaciones_acta(orden),
        "escala": escala,
        # Altos en mm (texto ya formateado con punto, no con coma) para repartir
        # el blanco de la hoja. None: los altos normales de la plantilla.
        "alto_obs_mm": alto_obs_mm,
        "alto_reserva_mm": alto_reserva_mm,
    }


def _render(contexto, escala, medidas=None):
    """Documento de WeasyPrint del acta con esa escala (sin escribir el PDF).

    ``medidas`` son las de ``_medidas_para_llenar_la_hoja``: sin ellas el acta
    sale con el alto normal del cuadro y de la reserva.
    """
    import weasyprint  # import local: en Windows dev se simula en las pruebas

    html = render_to_string(PLANTILLA, {**contexto, "escala": escala, **(medidas or {})})
    return weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).render()


def _caja(caja, clase):
    """Primera caja de WeasyPrint cuyo elemento tenga esa clase, o None.

    Se recorre a mano porque las cajas con ``position: fixed`` (el pie y las
    firmas) vienen envueltas en un ``AbsolutePlaceholder`` que guarda la caja
    real en ``_box``. Son internos de WeasyPrint, que va fijo en 70.0.
    """
    caja = getattr(caja, "_box", caja)
    elemento = getattr(caja, "element", None)
    if elemento is not None and clase in (elemento.get("class") or "").split():
        return caja
    for hija in getattr(caja, "children", None) or ():
        encontrada = _caja(hija, clase)
        if encontrada is not None:
            return encontrada
    return None


def _medidas_para_llenar_la_hoja(documento):
    """``{"alto_obs_mm", "alto_reserva_mm"}`` para que el acta llene la hoja, o None.

    Dos cosas se miden sobre la página ya maquetada:

    - El **pie real** (firmas + pie de página). La reserva del flujo es de
      11,6 em para el peor caso (nombre y cargo en dos renglones en las dos
      firmas); cuando el pie mide menos, esa diferencia es blanco regalado en
      todas las actas, así que la reserva se ajusta al pie medido más un aire.
    - El **sobrante al final de la hoja**, que junto con lo que libera la
      reserva se le suma al cuadro de observaciones, que es donde sirve
      (ahí se escribe a mano).

    Devuelve None si no hay nada que ganar o si no se pudo medir; en ese caso el
    acta sale con la disposición de siempre.
    """
    pagina = documento.pages[0]
    if not hasattr(pagina, "_page_box"):
        return None  # documento simulado en las pruebas de Windows
    try:
        caja_pagina = pagina._page_box
        cuadro = _caja(caja_pagina, "cuadro")
        reserva = _caja(caja_pagina, "reserva")
        pie = _caja(caja_pagina, "pie-hoja")
        if cuadro is None or reserva is None or pie is None:
            return None
        fondo = caja_pagina.content_box_y() + caja_pagina.height
        reserva_nueva = pie.margin_height() + AIRE_RESERVA_MM / MM_POR_PX
        libre = fondo - (reserva.position_y + reserva.margin_height())
        gana = libre + (reserva.margin_height() - reserva_nueva)
        alto_cuadro = cuadro.margin_height()
    except Exception:  # noqa: BLE001 - medir es opcional, el acta no depende de esto
        logger.warning("No se pudo medir el acta para repartir el blanco", exc_info=True)
        return None
    if gana * MM_POR_PX < SOBRA_MINIMA_MM:
        return None
    return {
        "alto_obs_mm": f"{(alto_cuadro + gana) * MM_POR_PX - COLCHON_MM:.1f}",
        "alto_reserva_mm": f"{reserva_nueva * MM_POR_PX:.1f}",
    }


def _escala_que_cabe(contexto):
    """``(escala, documento)`` de la escala más grande que entra en una hoja.

    Búsqueda binaria (3 renders en vez de 7): entrar en una hoja es monótono
    respecto del tamaño de la letra. Si no cabe ni con la letra más chica,
    devuelve esa y el acta sale en dos hojas.
    """
    izquierda, derecha = 0, len(ESCALAS) - 1
    mejor = None
    while izquierda <= derecha:
        medio = (izquierda + derecha) // 2
        documento = _render(contexto, ESCALAS[medio])
        if len(documento.pages) == 1:
            mejor = (ESCALAS[medio], documento)
            derecha = medio - 1
        else:
            izquierda = medio + 1
    if mejor is None:
        logger.warning(
            "El acta N° %s no cabe en una hoja ni con la letra más chica", contexto.get("numero")
        )
        mejor = (ESCALAS[-1], _render(contexto, ESCALAS[-1]))
    return mejor


def documento_acta(orden, request):
    """``(documento, escala)`` del acta ya acomodada, sin escribir el PDF todavía.

    Dos pasos: primero la escala (``_escala_que_cabe``) y después, si entre las
    observaciones y las firmas quedó blanco, se estira el cuadro de observaciones
    para repartirlo. Si al estirar se pasara a dos hojas, se queda el del primer
    paso. Las pruebas miden sobre este documento, que es el que se imprime.
    """
    contexto = contexto_acta(orden, request)
    escala, documento = _escala_que_cabe(contexto)
    medidas = _medidas_para_llenar_la_hoja(documento)
    if medidas is not None:
        estirado = _render(contexto, escala, medidas=medidas)
        if len(estirado.pages) == 1:
            documento = estirado
    return documento, escala


def renderizar_acta(orden, request):
    """PDF del acta en una hoja, con la letra más grande que entra y sin blanco al medio.

    Devuelve ``(bytes_del_pdf, escala)``.
    """
    documento, escala = documento_acta(orden, request)
    return documento.write_pdf(), escala
