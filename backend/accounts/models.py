from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROL_CHOICES = [
        ("superadmin", "Super Administrador"),
        ("admin", "Administrador"),
        ("tecnico", "Técnico"),
        ("lectura", "Solo lectura"),
    ]
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default="tecnico")
    # Sale en las actas que firma la cuenta (p. ej. el técnico de un mantenimiento).
    cargo = models.CharField(max_length=150, blank=True)
