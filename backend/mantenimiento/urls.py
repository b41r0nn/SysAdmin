from django.urls import path

from . import views

app_name = "mantenimiento"

urlpatterns = [
    path("", views.lista_planes, name="lista_planes"),
    path("planes/<int:pk>/", views.detalle_plan, name="detalle_plan"),
    path("planes/nuevo/", views.crear_plan, name="crear_plan"),
    path("planes/<int:pk>/editar/", views.editar_plan, name="editar_plan"),
    path("planes/<int:pk>/toggle/", views.toggle_plan, name="toggle_plan"),
    path("planes/<int:pk>/eliminar/", views.eliminar_plan, name="eliminar_plan"),
    path("ordenes/", views.lista_ordenes, name="lista_ordenes"),
    path("ordenes/nueva/", views.crear_orden, name="crear_orden"),
    path("ordenes/<int:pk>/", views.detalle_orden, name="detalle_orden"),
    path("ordenes/<int:pk>/editar/", views.editar_orden, name="editar_orden"),
    path("ordenes/<int:pk>/cerrar/", views.cerrar_orden, name="cerrar_orden"),
    path("ordenes/<int:pk>/eliminar/", views.eliminar_orden, name="eliminar_orden"),
    path("ordenes/<int:orden_pk>/repuestos/nuevo/", views.crear_repuesto, name="crear_repuesto"),
    path("repuestos/<int:pk>/editar/", views.editar_repuesto, name="editar_repuesto"),
    path("repuestos/<int:pk>/eliminar/", views.eliminar_repuesto, name="eliminar_repuesto"),
]
