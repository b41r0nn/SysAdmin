from django.conf import settings
from django.db import models

from inventario.models import TIPOS


ESTADOS_TICKET = [
    ("abierto", "Abierto"),
    ("en_proceso", "En proceso"),
    ("resuelto", "Resuelto"),
    ("cerrado", "Cerrado"),
    ("escalado", "Escalado"),
]

PRIORIDADES_TICKET = [
    ("baja", "Baja"),
    ("media", "Media"),
    ("alta", "Alta"),
]


class Ticket(models.Model):
    asunto = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    prioridad = models.CharField(max_length=20, choices=PRIORIDADES_TICKET, default="media")
    estado = models.CharField(max_length=20, choices=ESTADOS_TICKET, default="abierto")
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="tickets_solicitados",
        null=True,
        blank=True,
        verbose_name="Solicitante",
    )
    # Datos del solicitante en texto libre (formulario público, sin login)
    nombre_solicitante = models.CharField(max_length=150, blank=True, default="",
                                          verbose_name="Nombre del solicitante")
    area_solicitante = models.CharField(max_length=150, blank=True, default="",
                                        verbose_name="Área o departamento")
    contacto_solicitante = models.CharField(max_length=150, blank=True, default="",
                                            verbose_name="Correo o extensión de contacto")
    tipo_dispositivo = models.CharField(
        max_length=50, blank=True, default="", choices=TIPOS,
        verbose_name="Tipo de dispositivo",
    )
    numero_serie_etiqueta = models.CharField(
        max_length=100, blank=True, default="",
        verbose_name="Número de serie o etiqueta del equipo",
    )
    acciones_realizadas = models.TextField(
        blank=True, default="", verbose_name="Acciones realizadas",
    )
    tiempo_empleado_minutos = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Tiempo empleado (minutos)",
    )
    asignado_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="tickets_asignados",
        null=True,
        blank=True,
        verbose_name="Asignado a",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Ticket de soporte"
        verbose_name_plural = "Tickets de soporte"
        indexes = [
            models.Index(fields=["estado", "fecha_creacion"]),
        ]

    def __str__(self):
        return f"#{self.pk} · {self.asunto}"