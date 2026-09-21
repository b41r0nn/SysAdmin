from django.urls import path

from . import views

app_name = "yule"

urlpatterns = [
    path("", views.index, name="index"),
    path("configuracion/", views.configuracion, name="configuracion"),
    path("equipos/", views.equipos_lista, name="equipos_lista"),
    path("equipos/<int:pk>/", views.equipo_detalle, name="equipo_detalle"),
    path("equipos/sin-match/", views.equipos_sin_match, name="equipos_sin_match"),
    path("sincronizar/", views.sincronizar, name="sincronizar"),
    path("historial/", views.historial_sincronizaciones, name="historial"),
    path("api/test-conexion/", views.test_conexion_ocs, name="test_conexion"),
]
