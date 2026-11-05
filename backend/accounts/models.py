from django.contrib.auth.models import AbstractUser
from django.db import models

from accounts.permisos import administracion_roles_choices


class CustomUser(AbstractUser):
    # Copia de fábrica: es el respaldo que usa administracion_roles_choices
    # cuando la tabla Rol no existe todavía (primer migrate) o está vacía.
    ROL_CHOICES = [
        ("superadmin", "Super Administrador"),
        ("admin", "Administrador"),
        ("tecnico", "Técnico"),
        ("lectura", "Solo lectura"),
    ]
    # El campo sigue siendo CharField: la tabla Rol manda en los choices, no en
    # el tipo. Es llamable para que un rol nuevo salga sin migrar.
    rol = models.CharField(
        max_length=20, choices=administracion_roles_choices, default="tecnico"
    )
    # Sale en las actas que firma la cuenta (p. ej. el técnico de un mantenimiento).
    cargo = models.CharField(max_length=150, blank=True)
