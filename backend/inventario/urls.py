from django.urls import path

from . import views

app_name = "inventario"

urlpatterns = [
    # ── Activos CRUD ──────────────────────────────────────────────────────────
    path("", views.lista_activos, name="lista"),
    path("nuevo/", views.crear_activo, name="crear"),
    path("<int:pk>/", views.detalle_activo, name="detalle"),
    path("<int:pk>/editar/", views.editar_activo, name="editar"),
    path("<int:pk>/baja/", views.toggle_baja_activo, name="baja"),

    # ── Etiquetas QR ───────────────────────────────────────────────────────────
    path("<int:pk>/qr/", views.qr_imagen, name="qr_imagen"),
    path("<int:pk>/etiqueta/", views.qr_etiqueta_pdf, name="etiqueta"),
    path("etiquetas/", views.qr_etiquetas_masivas, name="etiquetas"),

    # ── 3C: Movimientos + Actas ───────────────────────────────────────────────
    path("<int:pk>/asignar/", views.asignar_activo, name="asignar"),
    path("<int:pk>/devolver/", views.devolver_activo, name="devolver"),
    path("<int:pk>/trasladar/", views.trasladar_activo, name="trasladar"),
    path("acta/<int:asignacion_pk>/pdf/", views.generar_acta_pdf, name="acta_pdf"),
    path("acta/<int:asignacion_pk>/subir/", views.subir_acta_firmada, name="subir_acta"),
    path("asignacion/<int:asignacion_pk>/editar/", views.editar_asignacion, name="editar_asignacion"),

    # ── Catálogo de Modelos ───────────────────────────────────────────────────
    path("catalogo/", views.lista_catalogo, name="catalogo_lista"),
    path("catalogo/nuevo/", views.crear_catalogo, name="catalogo_crear"),
    path("catalogo/<int:pk>/editar/", views.editar_catalogo, name="catalogo_editar"),
    path("catalogo/json/", views.catalogo_json, name="catalogo_json"),

    # ── Exportar Excel ────────────────────────────────────────────────────────
    path("exportar/opciones/", views.exportar_opciones, name="exportar_opciones"),

    # ── Importar Activos ───────────────────────────────────────────────────────
    path("importar/", views.importar_activos, name="importar"),
    path("importar/confirmar/", views.confirmar_importar_activos, name="importar_confirmar"),
    path("importar/plantilla/", views.descargar_plantilla_activos, name="importar_plantilla"),
]
