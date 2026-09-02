from django.contrib import admin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("nombre_completo", "documento_identidad", "cargo", "area", "estado", "fecha_creacion")
    list_filter = ("estado", "area")
    search_fields = ("nombre_completo", "documento_identidad", "cargo", "area")
    readonly_fields = ("fecha_creacion",)
    ordering = ("nombre_completo",)
