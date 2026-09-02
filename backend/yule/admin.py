from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils import timezone

from .models import EquipoOCS, SincronizacionLog, ConfiguracionYule
from .sync import sincronizar_equipos_ocs, buscar_posibles_matches


@admin.action(description="Sincronizar con OCS")
def action_sincronizar_ahora(modeladmin, request, queryset):
    """Acción para sincronizar OCS desde admin"""
    log, mensaje = sincronizar_equipos_ocs(usuario=request.user, force=True)
    
    if log.fue_exitosa:
        messages.success(request, mensaje)
    else:
        messages.error(request, mensaje)


class ConfiguracionYuleAdmin(admin.ModelAdmin):
    list_display = ("nombre", "ultima_sincronizacion_display", "frecuencia_sync_minutos", "auto_sync_habilitado", "activa")
    readonly_fields = ("fecha_creacion", "fecha_actualizacion", "ultima_sincronizacion")
    fieldsets = (
        ("Configuración", {
            "fields": ("nombre", "activa", "descripcion"),
        }),
        ("Sincronización Automática", {
            "fields": ("auto_sync_habilitado", "frecuencia_sync_minutos"),
            "description": "Configurar sincronización automática cada N minutos",
        }),
        ("Metadata", {
            "fields": ("creada_por", "fecha_creacion", "fecha_actualizacion", "ultima_sincronizacion"),
            "classes": ("collapse",),
        }),
    )
    
    def ultima_sincronizacion_display(self, obj):
        if obj.ultima_sincronizacion:
            return obj.ultima_sincronizacion.strftime("%Y-%m-%d %H:%M:%S")
        return "Nunca"
    ultima_sincronizacion_display.short_description = "Última sincronización"
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.creada_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(EquipoOCS)
class EquipoOCSAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_host",
        "id_ocs",
        "tipo_dispositivo",
        "estado_link",
        "mac_address_truncado",
        "ip_address",
        "dias_sin_reporte_display",
        "activo_local_link",
    )
    list_filter = (
        "tipo_dispositivo",
        "visto_en_ultima_sync",
        "activo_local__isnull",
        "fecha_creacion",
    )
    search_fields = ("nombre_host", "id_ocs", "mac_address", "usuario_dominio", "serial_bios")
    readonly_fields = (
        "id_ocs",
        "fecha_primera_deteccion",
        "fecha_creacion",
        "fecha_actualizacion",
        "dias_sin_reporte",
        "esta_vinculado",
    )
    
    fieldsets = (
        ("Identificación OCS", {
            "fields": ("id_ocs", "nombre_host", "tipo_dispositivo", "usuario_dominio"),
        }),
        ("Sistema Operativo", {
            "fields": ("so_nombre", "so_version"),
        }),
        ("Hardware", {
            "fields": ("procesador", "memoria_ram_mb", "almacenamiento_total_gb"),
        }),
        ("Identificadores", {
            "fields": ("serial_bios", "mac_address", "ip_address"),
        }),
        ("Inventario Local", {
            "fields": ("activo_local", "esta_vinculado"),
        }),
        ("Sincronización", {
            "fields": ("ultimo_reporte_ocs", "visto_en_ultima_sync", "dias_sin_reporte"),
        }),
        ("Metadata", {
            "fields": ("observaciones", "fecha_primera_deteccion", "fecha_creacion", "fecha_actualizacion"),
            "classes": ("collapse",),
        }),
    )
    
    def estado_link(self, obj):
        if obj.visto_en_ultima_sync:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Visto</span>'
            )
        else:
            return format_html(
                '<span style="color: red; font-weight: bold;">✗ No visto</span>'
            )
    estado_link.short_description = "Estado"
    
    def mac_address_truncado(self, obj):
        if obj.mac_address:
            return obj.mac_address[:17]
        return "—"
    mac_address_truncado.short_description = "MAC"
    
    def dias_sin_reporte_display(self, obj):
        dias = obj.dias_sin_reporte
        if dias is None:
            return "—"
        if dias == 0:
            return format_html('<span style="color: green;">Hoy</span>')
        elif dias < 7:
            return format_html(f'<span style="color: orange;">{dias}d</span>')
        else:
            return format_html(f'<span style="color: red;">{dias}d</span>')
    dias_sin_reporte_display.short_description = "Días sin reporte"
    
    def activo_local_link(self, obj):
        if obj.activo_local:
            url = f"/admin/inventario/activo/{obj.activo_local.id}/change/"
            return format_html(
                '<a href="{}">{}</a>',
                url,
                obj.activo_local.serial
            )
        return "—"
    activo_local_link.short_description = "Activo vinculado"


@admin.register(SincronizacionLog)
class SincronizacionLogAdmin(admin.ModelAdmin):
    list_display = (
        "fecha_inicio_display",
        "estado_badge",
        "equipos_detectados",
        "equipos_nuevos_badge",
        "equipos_actualizados",
        "duracion_display",
        "realizado_por",
    )
    list_filter = ("estado", "fecha_inicio", "realizado_por")
    readonly_fields = (
        "fecha_inicio",
        "fecha_fin",
        "duracion_segundos",
        "detalles_json",
    )
    search_fields = ("mensaje_error", "realizado_por__username")
    
    fieldsets = (
        ("Resultado", {
            "fields": ("estado", "mensaje_error"),
        }),
        ("Estadísticas", {
            "fields": (
                "equipos_detectados",
                "equipos_nuevos",
                "equipos_actualizados",
                "equipos_desaparecidos",
            ),
        }),
        ("Ejecución", {
            "fields": (
                "fecha_inicio",
                "fecha_fin",
                "duracion_segundos",
                "realizado_por",
            ),
        }),
        ("Detalles", {
            "fields": ("detalles_json",),
            "classes": ("collapse",),
        }),
    )
    
    def fecha_inicio_display(self, obj):
        return obj.fecha_inicio.strftime("%Y-%m-%d %H:%M:%S")
    fecha_inicio_display.short_description = "Fecha/Hora"
    
    def estado_badge(self, obj):
        colores = {
            "exitosa": "green",
            "fallo": "red",
            "parcial": "orange",
        }
        color = colores.get(obj.estado, "gray")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_estado_display()
        )
    estado_badge.short_description = "Estado"
    
    def equipos_nuevos_badge(self, obj):
        if obj.equipos_nuevos > 0:
            return format_html(
                '<span style="color: green; font-weight: bold;">+{}</span>',
                obj.equipos_nuevos
            )
        return "0"
    equipos_nuevos_badge.short_description = "Nuevos"
    
    def duracion_display(self, obj):
        if obj.duracion_segundos:
            return f"{obj.duracion_segundos}s"
        return "—"
    duracion_display.short_description = "Duración"
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


admin.site.register(ConfiguracionYule, ConfiguracionYuleAdmin)
admin.site.site_header = "SysAdmin — Panel de Administración"
