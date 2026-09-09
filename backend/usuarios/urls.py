from django.urls import path
from . import views

app_name = "usuarios"

urlpatterns = [
    path("", views.lista_usuarios, name="lista"),
    path("nuevo/", views.crear_usuario, name="crear"),
    path("importar/", views.importar_usuarios, name="importar"),
    path("importar/confirmar/", views.confirmar_importar_usuarios, name="importar_confirmar"),
    path("<int:pk>/", views.detalle_usuario, name="detalle"),
    path("<int:pk>/editar/", views.editar_usuario, name="editar"),
    path("<int:pk>/toggle/", views.toggle_estado_usuario, name="toggle_estado"),
]
