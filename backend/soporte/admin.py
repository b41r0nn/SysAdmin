from django.contrib import admin

from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("pk", "asunto", "prioridad", "estado", "solicitante_display", "asignado_a", "fecha_creacion")
    list_filter = ("estado", "prioridad")
    search_fields = ("asunto", "descripcion", "solicitante__username", "nombre_solicitante", "area_solicitante", "contacto_solicitante")
    readonly_fields = ("fecha_creacion", "fecha_actualizacion")

    @admin.display(description="Solicitante")
    def solicitante_display(self, obj):
        if obj.nombre_solicitante:
            return obj.nombre_solicitante
        return obj.solicitante.username if obj.solicitante else "—"