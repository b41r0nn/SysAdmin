from django.contrib import admin

from .models import ChecklistItem, OrdenMantenimiento, PlanMantenimiento, Repuesto


@admin.register(PlanMantenimiento)
class PlanMantenimientoAdmin(admin.ModelAdmin):
    list_display = ("activo", "tipo", "criticidad", "estado", "proxima_ejecucion")
    list_filter = ("tipo", "criticidad", "estado")
    search_fields = ("activo__serial", "activo__marca", "activo__modelo")


@admin.register(OrdenMantenimiento)
class OrdenMantenimientoAdmin(admin.ModelAdmin):
    list_display = ("activo", "tipo", "estado", "prioridad", "fecha_apertura", "fecha_cierre")
    list_filter = ("tipo", "estado", "prioridad")
    search_fields = ("activo__serial", "activo__marca", "activo__modelo", "tecnico_asignado")


@admin.register(Repuesto)
class RepuestoAdmin(admin.ModelAdmin):
    list_display = ("orden", "nombre", "cantidad")
    search_fields = ("nombre", "referencia", "orden__activo__serial")


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("descripcion", "plan", "orden", "completado", "posicion")
    list_filter = ("completado",)
    search_fields = ("descripcion",)
