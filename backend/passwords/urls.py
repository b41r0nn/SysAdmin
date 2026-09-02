from django.urls import path

from . import views

app_name = "passwords"

urlpatterns = [
    path("", views.index, name="index"),
    path("vaults/nuevo/", views.vault_crear, name="vault_crear"),
    path("vaults/<int:pk>/editar/", views.vault_editar, name="vault_editar"),
    path("vaults/<int:pk>/eliminar/", views.vault_eliminar, name="vault_eliminar"),
    path("vaults/<int:vault_id>/credenciales/", views.credenciales_lista, name="credenciales_lista"),
    path("vaults/<int:vault_id>/credenciales/export/excel/", views.credenciales_export, name="credenciales_export"),
    path("vaults/<int:vault_id>/credenciales/nuevo/", views.credencial_crear, name="credencial_crear"),
    path("vaults/<int:vault_id>/credenciales/<int:pk>/editar/", views.credencial_editar, name="credencial_editar"),
    path("vaults/<int:vault_id>/credenciales/<int:pk>/eliminar/", views.credencial_eliminar, name="credencial_eliminar"),
    path("vaults/<int:vault_id>/credenciales/<int:pk>/secreto/", views.credencial_secreto, name="credencial_secreto"),
    path("vaults/<int:vault_id>/logs/", views.logs, name="logs"),
]
