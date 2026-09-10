from django.contrib import admin

from .models import ConfiguracionSistema, RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "modulo", "accion", "objeto_tipo", "objeto_id", "ip")
    list_filter = ("modulo", "accion")
    search_fields = ("detalle", "usuario__username", "objeto_tipo")
    date_hierarchy = "fecha"
    readonly_fields = [
        "fecha",
        "usuario",
        "modulo",
        "accion",
        "objeto_tipo",
        "objeto_id",
        "detalle",
        "ip",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConfiguracionSistema)
class ConfiguracionSistemaAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_empresa",
        "nit",
        "direccion",
        "telefono",
        "email_contacto",
        "fecha_actualizacion",
    )

    def has_add_permission(self, request):
        return not ConfiguracionSistema.objects.exists()