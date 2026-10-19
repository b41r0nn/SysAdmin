"""Vistas de inventario, agrupadas por tema en submódulos."""
from .activos import (  # noqa: F401
    crear_activo,
    detalle_activo,
    editar_activo,
    lista_activos,
    software_activo,
    software_global,
    toggle_baja_activo,
)
from .movimientos import (  # noqa: F401
    asignar_activo,
    devolver_activo,
    editar_asignacion,
    generar_acta_pdf,
    subir_acta_firmada,
    trasladar_activo,
)
from .qr import (  # noqa: F401
    qr_etiqueta_pdf,
    qr_etiquetas_masivas,
    qr_imagen,
    qr_publico,
    qr_publico_token,
)
from .catalogo import (  # noqa: F401
    catalogo_json,
    crear_catalogo,
    editar_catalogo,
    lista_catalogo,
)
from .excel import (  # noqa: F401
    confirmar_importar_activos,
    descargar_plantilla_activos,
    exportar_opciones,
    importar_activos,
)
