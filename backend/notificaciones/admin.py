from django.contrib import admin

from .models import Notificacion, NotificacionEmail


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


@admin.register(NotificacionEmail)
class NotificacionEmailAdmin(admin.ModelAdmin):
    list_display = ("destinatario", "asunto", "enviado", "intentos", "fecha_creacion", "fecha_enviado")
    list_filter = ("enviado", "intentos", "fecha_creacion")
    search_fields = ("destinatario", "asunto")
    # `error` es de solo lectura, no excluido: es lo que el servidor contestó y
    # es el único diagnóstico que hay cuando la cola no sale, así que se sigue
    # viendo. Lo que se cierra es la segunda puerta —editarlo a mano, que no
    # tiene ningún uso legítimo y sí sirve para fabricar un rastro falso—; de
    # que el valor no traiga la credencial se encarga
    # `administracion.errores_correo` al escribirlo.
    readonly_fields = ("fecha_creacion", "fecha_enviado", "error")

    @admin.action(description="Reintentar las seleccionadas (resetear intentos)")
    def reintentar(self, request, queryset):
        queryset.update(enviado=False, intentos=0, error="")

    actions = [reintentar]
