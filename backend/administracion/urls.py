from django.urls import path

from . import views

app_name = "administracion"

urlpatterns = [
    path("auditoria/", views.lista_auditoria, name="lista_auditoria"),
    path("configuracion/", views.configuracion, name="configuracion"),
]