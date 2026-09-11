from django.conf import settings
from django.template.loader import render_to_string


def acta_pdf_bytes(asignacion):
    """Renderiza el acta de asignación como bytes.

    Es el único punto de generación del PDF: la vista de descarga y la cola de
    emails usan esta misma función para que nunca se desincronicen.
    """
    import weasyprint  # import local: en Windows dev se mockea en tests

    html = render_to_string("inventario/acta_pdf.html", {"asignacion": asignacion})
    return weasyprint.HTML(string=html, base_url=settings.BASE_DIR).write_pdf()