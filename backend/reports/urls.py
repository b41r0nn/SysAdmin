from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.index, name="index"),
    path("inventario/pdf/", views.inventario_pdf, name="inventario_pdf"),
    path("usuarios/pdf/", views.usuarios_pdf, name="usuarios_pdf"),
    path("inventario/excel/", views.inventario_excel, name="inventario_excel"),
    path("movimientos/excel/", views.movimientos_excel, name="movimientos_excel"),
    path("usuarios/excel/", views.usuarios_excel, name="usuarios_excel"),
    path("costos/excel/", views.costos_excel, name="costos_excel"),
    path("mantenimiento/excel/", views.mantenimiento_excel, name="mantenimiento_excel"),
]
