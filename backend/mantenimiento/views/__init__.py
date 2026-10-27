"""Vistas de mantenimiento, agrupadas por tema en submódulos."""
from .ordenes import (  # noqa: F401
    crear_foto,
    crear_orden,
    crear_repuesto,
    detalle_orden,
    editar_orden,
    editar_repuesto,
    eliminar_foto,
    eliminar_orden,
    eliminar_repuesto,
    lista_ordenes,
    toggle_foto_acta,
)
from .actas import (  # noqa: F401
    acta_pdf,
    subir_acta_firmada,
)
from .ejecucion import (  # noqa: F401
    cerrar_orden,
    iniciar_preventivo,
    marcar_punto,
    nuevo,
    reabrir_orden,
)
from .plantillas import (  # noqa: F401
    crear_plantilla,
    editar_plantilla,
    lista_plantillas,
)
from .reportes import (  # noqa: F401
    calendario,
    calendario_eventos,
    hoja_de_vida,
    hoja_de_vida_buscar,
    hoja_de_vida_pdf,
    orden_pdf,
    reporte_activos_pdf,
    reporte_mantenimientos_pdf,
    reportar,
)
from .tablero import (  # noqa: F401
    inicio,
    programar,
)
