from django.urls import path

from . import views

app_name = "administracion"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("auditoria/", views.lista_auditoria, name="lista_auditoria"),
    path("cuentas/", views.lista_cuentas, name="cuentas"),
    path("cuentas/crear/", views.crear_cuenta, name="crear_cuenta"),
    path("cuentas/<int:pk>/rol/", views.cambiar_rol_cuenta, name="cambiar_rol"),
    path("cuentas/<int:pk>/estado/", views.toggle_cuenta, name="toggle_cuenta"),
    path("cuentas/<int:pk>/password/", views.resetear_password, name="resetear_password"),
    path("configuracion/", views.configuracion, name="configuracion"),
    path("modulos/", views.modulos, name="modulos"),
    path("roles/", views.roles, name="roles"),
    path("correo/", views.correo, name="correo"),
    path("seguridad/", views.seguridad, name="seguridad"),
    path("datos/", views.datos, name="datos"),
]
