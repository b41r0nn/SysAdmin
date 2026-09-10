from datetime import date

from django.conf import settings
from django.db import models


ESTADOS_PRESTAMO = [
    ("activo", "Activo"),
    ("vencido", "Vencido"),
    ("devuelto", "Devuelto"),
]


class Prestamo(models.Model):
    """Préstamo de un activo de inventario a un usuario interno."""

    activo = models.ForeignKey(
        "inventario.Activo",
        on_delete=models.PROTECT,
        related_name="prestamos",
        verbose_name="Equipo",
    )
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="prestamos_solicitados",
        verbose_name="Solicitante",
    )
    fecha_prestamo = models.DateField(default=date.today, verbose_name="Fecha de préstamo")
    fecha_devolucion_prevista = models.DateField(null=True, blank=True, verbose_name="Devolución prevista")
    fecha_devolucion = models.DateField(null=True, blank=True, verbose_name="Fecha de devolución")
    destino = models.CharField(max_length=200, blank=True, verbose_name="Destino / motivo")
    observaciones = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_prestamo", "-fecha_creacion"]
        verbose_name = "Préstamo"
        verbose_name_plural = "Préstamos"
        indexes = [
            models.Index(fields=["fecha_prestamo", "fecha_devolucion_prevista"]),
        ]

    def __str__(self):
        return f"{self.activo} → {self.solicitante.username} ({self.fecha_prestamo})"

    @property
    def estado(self):
        if self.fecha_devolucion:
            return "devuelto"
        if self.fecha_devolucion_prevista and self.fecha_devolucion_prevista < date.today():
            return "vencido"
        return "activo"

    @property
    def estado_display(self):
        return dict(ESTADOS_PRESTAMO)[self.estado]

    def dias_retraso(self):
        if self.estado != "vencido":
            return 0
        return (date.today() - self.fecha_devolucion_prevista).days