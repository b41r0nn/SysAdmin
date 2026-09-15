import os

from django.conf import settings
from django.template.loader import render_to_string

LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "img", "logo_redihos_mark.png")


def acta_pdf_bytes(asignacion):
    """Renderiza el acta de asignación como bytes.

    Es el único punto de generación del PDF: la vista de descarga y la cola de
    emails usan esta misma función para que nunca se desincronicen.
    """
    import weasyprint  # import local: en Windows dev se mockea en tests

    from administracion.models import ConfiguracionSistema

    html = render_to_string(
        "inventario/acta_pdf.html",
        {
            "asignacion": asignacion,
            "config": ConfiguracionSistema.get_config(),
            "logo_path": LOGO_PATH,
        },
    )
    # base_url debe ser string; settings.BASE_DIR es un pathlib.Path en Docker
    return weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()