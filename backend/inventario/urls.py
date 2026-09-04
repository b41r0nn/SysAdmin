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

    # ── 3C: Movimientos + Actas ───────────────────────────────────────────────
    path("<int:pk>/asignar/", views.asignar_activo, name="asignar"),
    path("<int:pk>/devolver/", views.devolver_activo, name="devolver"),
    path("<int:pk>/trasladar/", views.trasladar_activo, name="trasladar"),
    path("acta/<int:asignacion_pk>/pdf/", views.generar_acta_pdf, name="acta_pdf"),
    path("acta/<int:asignacion_pk>/subir/", views.subir_acta_firmada, name="subir_acta"),

    # ── Catálogo de Modelos ───────────────────────────────────────────────────
    path("catalogo/", views.lista_catalogo, name="catalogo_lista"),
    path("catalogo/nuevo/", views.crear_catalogo, name="catalogo_crear"),
    path("catalogo/<int:pk>/editar/", views.editar_catalogo, name="catalogo_editar"),
    path("catalogo/json/", views.catalogo_json, name="catalogo_json"),

    # ── Exportar Excel ────────────────────────────────────────────────────────
    path("exportar/opciones/", views.exportar_opciones, name="exportar_opciones"),
]
