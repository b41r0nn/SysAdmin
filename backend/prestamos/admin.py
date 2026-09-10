from django.contrib import admin

from .models import Prestamo


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "activo",
        "solicitante",
        "fecha_prestamo",
        "fecha_devolucion_prevista",
        "fecha_devolucion",
    )
    list_filter = ("fecha_prestamo",)
    search_fields = ("activo__serial", "activo__marca", "solicitante__username")