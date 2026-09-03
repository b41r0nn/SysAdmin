from django.contrib import admin

from .models import Categoria, Documento


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "orden")
    search_fields = ("nombre",)


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "categoria", "tipo_documento", "version", "activo", "fecha_actualizacion")
    list_filter = ("tipo_documento", "categoria", "activo")
    search_fields = ("titulo", "descripcion", "version")
    date_hierarchy = "fecha_actualizacion"
