from django.urls import path

from . import views

app_name = "mantenimiento"

urlpatterns = [
    path("", views.lista_ordenes, name="lista_ordenes"),
    path("planes/", views.lista_planes, name="lista_planes"),
    path("calendario/", views.calendario, name="calendario"),
    path("calendario/eventos/", views.calendario_eventos, name="calendario_eventos"),
    path("reportar/", views.reportar, name="reportar"),
    path("checklist/<int:pk>/toggle/", views.toggle_checklist, name="toggle_checklist"),
    path("planes/<int:pk>/", views.detalle_plan, name="detalle_plan"),
    path("planes/nuevo/", views.crear_plan, name="crear_plan"),
    path("planes/<int:pk>/editar/", views.editar_plan, name="editar_plan"),
    path("planes/<int:pk>/toggle/", views.toggle_plan, name="toggle_plan"),
    path("planes/<int:pk>/eliminar/", views.eliminar_plan, name="eliminar_plan"),
    path("ordenes/nueva/", views.crear_orden, name="crear_orden"),
    path("ordenes/estado-partes/", views.estado_partes_partial, name="estado_partes_partial"),
    path("ordenes/<int:pk>/", views.detalle_orden, name="detalle_orden"),
    path("ordenes/<int:pk>/editar/", views.editar_orden, name="editar_orden"),
    path("ordenes/<int:pk>/cerrar/", views.cerrar_orden, name="cerrar_orden"),
    path("ordenes/<int:pk>/eliminar/", views.eliminar_orden, name="eliminar_orden"),
    path("ordenes/<int:pk>/pdf/", views.orden_pdf, name="orden_pdf"),
    path("ordenes/<int:pk>/fotos/nueva/", views.crear_foto, name="crear_foto"),
    path("fotos/<int:pk>/eliminar/", views.eliminar_foto, name="eliminar_foto"),
    path("ordenes/<int:pk>/checklist/nuevo/", views.crear_item_checklist, name="crear_item_checklist"),
    path("hoja-de-vida/", views.hoja_de_vida_buscar, name="hoja_de_vida_buscar"),
    path("hoja-de-vida/<int:activo_pk>/", views.hoja_de_vida, name="hoja_de_vida"),
    path("hoja-de-vida/<int:activo_pk>/pdf/", views.hoja_de_vida_pdf, name="hoja_de_vida_pdf"),
    path("reporte/pdf/", views.reporte_mantenimientos_pdf, name="reporte_mantenimientos_pdf"),
    path("reporte/activos/pdf/", views.reporte_activos_pdf, name="reporte_activos_pdf"),
    path("ordenes/<int:orden_pk>/repuestos/nuevo/", views.crear_repuesto, name="crear_repuesto"),
    path("repuestos/<int:pk>/editar/", views.editar_repuesto, name="editar_repuesto"),
    path("repuestos/<int:pk>/eliminar/", views.eliminar_repuesto, name="eliminar_repuesto"),
]
