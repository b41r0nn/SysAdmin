from django.urls import path

from . import views

app_name = "licencias"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nuevo/", views.crear, name="crear"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/eliminar/", views.eliminar, name="eliminar"),
    path("exportar/excel/", views.exportar_excel, name="exportar_excel"),
    path("exportar/pdf/", views.exportar_pdf, name="exportar_pdf"),
]