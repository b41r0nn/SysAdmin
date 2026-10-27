from django.contrib import admin

from .models import (
    ChecklistItem,
    OrdenMantenimiento,
    PlantillaChecklist,
    PuntoPlantilla,
    Repuesto,
)


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
    list_display = ("descripcion", "orden", "seccion", "resultado", "posicion")
    list_filter = ("resultado",)
    search_fields = ("descripcion",)


class PuntoPlantillaInline(admin.TabularInline):
    model = PuntoPlantilla
    extra = 0
    fields = ("posicion", "seccion", "descripcion", "aplica_en_garantia", "activo")


@admin.register(PlantillaChecklist)
class PlantillaChecklistAdmin(admin.ModelAdmin):
    list_display = ("tipo_dispositivo", "frecuencia_meses", "fecha_actualizacion")
    inlines = [PuntoPlantillaInline]
