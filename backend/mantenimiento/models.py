from django.db import models
from django.utils import timezone


TIPOS_MANTENIMIENTO = [
    ("preventivo", "Preventivo"),
    ("correctivo", "Correctivo"),
]

ESTADOS_PLAN = [
    ("activo", "Activo"),
    ("pausado", "Pausado"),
]

ESTADOS_ORDEN = [
    ("abierta", "Abierta"),
    ("en_proceso", "En proceso"),
    ("cerrada", "Cerrada"),
    ("cancelada", "Cancelada"),
]

PRIORIDADES = [
    ("baja", "Baja"),
    ("media", "Media"),
    ("alta", "Alta"),
]


class PlanMantenimiento(models.Model):
    activo = models.ForeignKey(
        "inventario.Activo",
        on_delete=models.PROTECT,
        related_name="planes_mantenimiento",
    )
    tipo = models.CharField(max_length=20, choices=TIPOS_MANTENIMIENTO)
    frecuencia_dias = models.PositiveIntegerField(null=True, blank=True)
    fecha_inicio = models.DateField(null=True, blank=True)
    proxima_ejecucion = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS_PLAN, default="activo")
    responsable = models.CharField(max_length=150, blank=True)
    observaciones = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Plan de Mantenimiento"
        verbose_name_plural = "Planes de Mantenimiento"

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.activo.serial}"


class OrdenMantenimiento(models.Model):
    plan = models.ForeignKey(
        PlanMantenimiento,
        on_delete=models.SET_NULL,
        related_name="ordenes",
        null=True,
        blank=True,
    )
    activo = models.ForeignKey(
        "inventario.Activo",
        on_delete=models.PROTECT,
        related_name="ordenes_mantenimiento",
    )
    tipo = models.CharField(max_length=20, choices=TIPOS_MANTENIMIENTO)
    estado = models.CharField(max_length=20, choices=ESTADOS_ORDEN, default="abierta")
    prioridad = models.CharField(max_length=20, choices=PRIORIDADES, default="media")
    fecha_apertura = models.DateField(default=timezone.now)
    fecha_cierre = models.DateField(null=True, blank=True)
    tecnico_asignado = models.CharField(max_length=150, blank=True)
    descripcion = models.TextField(blank=True)
    diagnostico = models.TextField(blank=True)
    acciones = models.TextField(blank=True)
    costo_estimado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    costo_real = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_apertura", "-fecha_creacion"]
        verbose_name = "Orden de Mantenimiento"
        verbose_name_plural = "Ordenes de Mantenimiento"

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.activo.serial}"


class Repuesto(models.Model):
    orden = models.ForeignKey(
        OrdenMantenimiento,
        on_delete=models.CASCADE,
        related_name="repuestos",
    )
    nombre = models.CharField(max_length=150)
    referencia = models.CharField(max_length=120, blank=True)
    cantidad = models.PositiveIntegerField(default=1)
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Repuesto"
        verbose_name_plural = "Repuestos"

    def __str__(self):
        return f"{self.nombre} ({self.cantidad})"
