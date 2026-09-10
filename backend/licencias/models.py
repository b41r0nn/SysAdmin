from datetime import date

from django.db import models


TIPOS_LICENCIA = [
    ("volumen", "Volumen"),
    ("individual", "Individual"),
    ("oem", "OEM / Preinstalada"),
    ("suscripcion", "Suscripción"),
]

ESTADOS_LICENCIA = [
    ("activa", "Activa"),
    ("por_vencer", "Por vencer"),
    ("vencida", "Vencida"),
    ("cancelada", "Cancelada"),
]

DIAS_AVISO_VENCIMIENTO = 7


class LicenciaSoftware(models.Model):
    """Licencia de software (producto, clave/serial, cobertura y vigencia)."""

    nombre = models.CharField(max_length=150, verbose_name="Software")
    version = models.CharField(max_length=50, blank=True, verbose_name="Versión")
    proveedor = models.CharField(max_length=120, blank=True, verbose_name="Proveedor / editor")
    clave = models.CharField(max_length=255, blank=True, verbose_name="Clave / serial")
    tipo = models.CharField(max_length=20, choices=TIPOS_LICENCIA, default="volumen", verbose_name="Tipo de licencia")
    cantidad = models.PositiveIntegerField(default=1, verbose_name="Cantidad (usuarios / equipos)")
    fecha_compra = models.DateField(null=True, blank=True, verbose_name="Fecha de compra")
    fecha_vencimiento = models.DateField(null=True, blank=True, verbose_name="Fecha de vencimiento")
    costo = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS_LICENCIA, default="activa")
    responsable = models.CharField(max_length=120, blank=True)
    activos = models.ManyToManyField(
        "inventario.Activo",
        blank=True,
        related_name="licencias",
        verbose_name="Equipos cubiertos",
    )
    observaciones = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre", "version"]
        verbose_name = "Licencia de software"
        verbose_name_plural = "Licencias de software"

    def __str__(self):
        texto = self.nombre if not self.version else f"{self.nombre} {self.version}"
        return f"{texto} · #{self.pk}"

    @property
    def estado_efectivo(self):
        """Estado real según vencimiento: vencida > por_vencer > estado manual."""
        hoy = date.today()
        if self.estado == "cancelada":
            return "cancelada"
        if self.fecha_vencimiento:
            dias = (self.fecha_vencimiento - hoy).days
            if dias < 0:
                return "vencida"
            if dias <= DIAS_AVISO_VENCIMIENTO:
                return "por_vencer"
        return "activa"

    @property
    def estado_efectivo_display(self):
        return dict(ESTADOS_LICENCIA)[self.estado_efectivo]

    def dias_para_vencer(self):
        if not self.fecha_vencimiento:
            return None
        return (self.fecha_vencimiento - date.today()).days