from django.contrib import admin

from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("pk", "asunto", "prioridad", "estado", "solicitante", "asignado_a", "fecha_creacion")
    list_filter = ("estado", "prioridad")
    search_fields = ("asunto", "descripcion", "solicitante__username")
    readonly_fields = ("fecha_creacion", "fecha_actualizacion")