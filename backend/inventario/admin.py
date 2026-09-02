from django.contrib import admin

from .models import ActaAsignacion, Activo, Asignacion, CatalogoModelo, Movimiento


@admin.register(CatalogoModelo)
class CatalogoModeloAdmin(admin.ModelAdmin):
    list_display = ("tipo_dispositivo", "marca", "modelo")
    list_filter = ("tipo_dispositivo",)
    search_fields = ("marca", "modelo")


@admin.register(Activo)
class ActivoAdmin(admin.ModelAdmin):
    list_display = ("serial", "tipo_dispositivo", "marca", "modelo", "estado", "ubicacion_fisica")
    list_filter = ("tipo_dispositivo", "estado")
    search_fields = ("serial", "marca", "modelo", "imei")


@admin.register(Asignacion)
class AsignacionAdmin(admin.ModelAdmin):
    list_display = ("activo", "usuario", "fecha_asignacion", "activa")
    list_filter = ("activa",)


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ("activo", "tipo", "fecha", "realizado_por")
    list_filter = ("tipo",)


@admin.register(ActaAsignacion)
class ActaAsignacionAdmin(admin.ModelAdmin):
    list_display = ("asignacion", "fecha_generacion")
