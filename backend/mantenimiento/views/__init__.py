"""Vistas de mantenimiento, agrupadas por tema en submódulos."""
from .ordenes import (  # noqa: F401
    cerrar_orden,
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
)
from .planes import (  # noqa: F401
    crear_plan,
    detalle_plan,
    editar_plan,
    eliminar_plan,
    lista_planes,
    toggle_plan,
)
from .ejecucion import (  # noqa: F401
    iniciar_preventivo,
    marcar_punto,
    nuevo,
)
from .legado import (  # noqa: F401
    crear_item_checklist,
    estado_partes_partial,
    toggle_checklist,
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
