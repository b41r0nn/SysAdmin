from django.contrib import admin

from .models import AccesoLog, Credencial, Vault


@admin.register(Vault)
class VaultAdmin(admin.ModelAdmin):
    list_display = ("nombre", "creado_por", "fecha_creacion")
    search_fields = ("nombre",)


@admin.register(Credencial)
class CredencialAdmin(admin.ModelAdmin):
    list_display = ("titulo", "vault", "estado", "fecha_expiracion")
    list_filter = ("estado", "vault")
    search_fields = ("titulo", "usuario", "url")


@admin.register(AccesoLog)
class AccesoLogAdmin(admin.ModelAdmin):
    list_display = ("accion", "vault", "credencial", "usuario", "fecha")
    list_filter = ("accion", "vault", "usuario")
    search_fields = ("accion", "detalle")
