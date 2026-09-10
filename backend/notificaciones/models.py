from django.conf import settings
from django.db import models


TIPOS = [
    ("garantia", "Garantía"),
    ("mantenimiento", "Mantenimiento"),
    ("acta", "Acta de asignación"),
    ("ocs", "Equipos OCS"),
    ("licencia", "Licencias / contratos"),
    ("aviso", "Aviso del sistema"),
]


class Notificacion(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notificaciones",
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True)
    objetokey = models.CharField(max_length=150, blank=True)
    leida = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        indexes = [
            models.Index(fields=["usuario", "leida", "fecha_creacion"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "tipo", "objetokey"],
                condition=~models.Q(objetokey=""),
                name="uniq_notificacion_objeto",
            ),
        ]

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.usuario} · {self.titulo}"