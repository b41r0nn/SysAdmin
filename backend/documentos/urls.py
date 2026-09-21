from django.urls import path

from . import views

app_name = "documentos"

urlpatterns = [
    path("", views.lista_documentos, name="lista"),
    path("nuevo/", views.crear_documento, name="crear"),
    path("<int:pk>/editar/", views.editar_documento, name="editar"),
    path("<int:pk>/eliminar/", views.eliminar_documento, name="eliminar"),
    path("<int:pk>/ver/", views.ver_documento, name="ver"),
    path("<int:pk>/descargar/", views.descargar_documento, name="descargar"),

    # Categorías
    path("categorias/", views.lista_categorias, name="categorias_lista"),
    path("categorias/nueva/", views.crear_categoria, name="categoria_crear"),
    path("categorias/<int:pk>/editar/", views.editar_categoria, name="categoria_editar"),
    path("categorias/<int:pk>/eliminar/", views.eliminar_categoria, name="categoria_eliminar"),
]
