from django.contrib import admin

from .models import Notificacion


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ("usuario", "tipo", "titulo", "leida", "fecha_creacion")
    list_filter = ("tipo", "leida", "fecha_creacion")
    search_fields = ("usuario__username", "titulo", "mensaje")
    readonly_fields = ("fecha_creacion",)
    list_select_related = ("usuario",)

    @admin.action(description="Marcar como leídas las seleccionadas")
    def marcar_leidas(self, request, queryset):
        queryset.update(leida=True)

    actions = [marcar_leidas]