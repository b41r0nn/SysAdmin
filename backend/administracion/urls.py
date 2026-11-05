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
    path("modulos/<str:clave>/estado/", views.toggle_modulo, name="toggle_modulo"),
    path("roles/", views.roles, name="roles"),
    path("roles/<str:rol>/<str:modulo>/", views.guardar_permiso, name="guardar_permiso"),
    path("correo/", views.correo, name="correo"),
    path("correo/probar/", views.probar_correo, name="probar_correo"),
    path("correo/reintentar/", views.reintentar_correos, name="reintentar_correos"),
    path("seguridad/", views.seguridad, name="seguridad"),
    path("datos/", views.datos, name="datos"),
    path("datos/simular/", views.simular_limpieza, name="simular_limpieza"),
]
