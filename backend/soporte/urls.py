from django.urls import path

from . import views

app_name = "soporte"

urlpatterns = [
    path("", views.lista_tickets, name="lista"),
    path("reportar-publico/", views.reportar_publico, name="reportar_publico"),
    path("exportar/", views.tickets_excel, name="excel"),
    path("nuevo/", views.crear_ticket, name="crear"),
    path("<int:pk>/", views.detalle_ticket, name="detalle"),
    path("<int:pk>/editar/", views.editar_ticket, name="editar"),
    path("<int:pk>/asignar/", views.asignar_ticket, name="asignar"),
    path("<int:pk>/estado/", views.cambiar_estado, name="cambiar_estado"),
    path("<int:pk>/escalar/", views.escalar_ticket, name="escalar"),
]