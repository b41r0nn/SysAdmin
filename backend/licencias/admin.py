from django.contrib import admin

from .models import LicenciaSoftware


@admin.register(LicenciaSoftware)
class LicenciaSoftwareAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nombre",
        "version",
        "proveedor",
        "tipo",
        "cantidad",
        "estado",
        "fecha_vencimiento",
    )
    list_filter = ("tipo", "estado")
    search_fields = ("nombre", "proveedor", "responsable")
    filter_horizontal = ("activos",)