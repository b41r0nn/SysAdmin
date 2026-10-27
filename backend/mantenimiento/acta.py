"""Acta de mantenimiento en una sola hoja carta (§B7 del diseño).

Se arma siempre desde ``OrdenMantenimiento.datos_acta``, la foto congelada al
cerrar, más lo que ya es de la orden (checklist, fotos, repuestos, textos). Si
el contenido no cabe en una hoja, se prueba con letra más pequeña (``escala``).
"""

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse

from administracion.models import ConfiguracionSistema
from inventario.views.qr import _qr_data_uri

from . import services
from .models import FORMATO_ACTUAL, MAX_FOTOS_ACTA

PLANTILLA = "mantenimiento/acta_pdf.html"
# 0 es la letra normal; cada escala achica la letra y las fotos (ver la plantilla).
ESCALAS = (0, 1, 2, 3)
PARES_POR_FILA = 3
VACIO = "—"


def url_hoja_de_vida(request, activo):
    """URL absoluta de la hoja de vida del equipo, la que abre el QR del acta."""
    path = reverse("mantenimiento:hoja_de_vida", args=[activo.pk])
    base = (settings.QR_BASE_URL or "").strip()
    if base:
        return f"{base.rstrip('/')}{path}"
    return request.build_absolute_uri(path)


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


def contexto_acta(orden, request, escala: int = 0):
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
    }


def renderizar_acta(orden, request):
    """PDF del acta en una hoja, con la primera escala que cabe (o la última).

    Devuelve ``(bytes_del_pdf, escala)``.
    """
    import weasyprint  # import local: en Windows dev se simula en las pruebas

    contexto = contexto_acta(orden, request)
    documento = None
    for escala in ESCALAS:
        contexto["escala"] = escala
        html = render_to_string(PLANTILLA, contexto)
        documento = weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).render()
        if len(documento.pages) == 1:
            break
    return documento.write_pdf(), escala
