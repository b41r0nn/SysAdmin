from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone

from inventario.models import _ver_tipo


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
    ("reportada", "Reportada"),
]

PRIORIDADES = [
    ("baja", "Baja"),
    ("media", "Media"),
    ("alta", "Alta"),
]

CRITICIDADES = [
    ("baja", "Baja"),
    ("media", "Media"),
    ("alta", "Alta"),
]

# Secciones que se ofrecen al agregar un punto a un checklist. Es solo una
# sugerencia: la sección de un punto es texto libre.
SECCIONES_SUGERIDAS = ["Hardware", "Limpieza", "Mantenimiento lógico"]

# Formato de una orden: 1 es el de antes del rediseño (checklist fijo y estado
# de partes); 2 es el actual (checklist copiado de la plantilla).
FORMATO_ANTERIOR = 1
FORMATO_ACTUAL = 2


class PlanMantenimiento(models.Model):
    tipo_dispositivo = models.CharField(
        max_length=50,
        verbose_name="Categoría de equipo",
    )
    tipo = models.CharField(max_length=20, choices=TIPOS_MANTENIMIENTO)
    criticidad = models.CharField(max_length=20, choices=CRITICIDADES, default="media")
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
        return f"{self.get_tipo_display()} · {self.tipo_dispositivo}"


class OrdenMantenimiento(models.Model):
    plan = models.ForeignKey(
        PlanMantenimiento,
        on_delete=models.SET_NULL,
        related_name="ordenes",
        null=True,
        blank=True,
    )
    ticket = models.ForeignKey(
        "soporte.Ticket",
        on_delete=models.SET_NULL,
        related_name="ordenes",
        null=True,
        blank=True,
        verbose_name="Ticket de soporte",
    )
    reportado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="ordenes_reportadas",
        null=True,
        blank=True,
        verbose_name="Reportado por",
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
    foto = models.ImageField(
        upload_to="mantenimiento/fotos/",
        null=True,
        blank=True,
        verbose_name="Foto del problema",
    )
    diagnostico = models.TextField(blank=True)
    acciones = models.TextField(blank=True)

    accion_limpieza_general = models.BooleanField(default=False)
    accion_mantenimiento_logico = models.BooleanField(default=False)
    accion_cambio_pasta_termica = models.BooleanField(default=False)
    accion_cambio_parte = models.BooleanField(default=False)
    accion_cambio_parte_detalle = models.CharField(max_length=255, blank=True)
    estado_partes = models.JSONField(default=dict, blank=True)

    costo_estimado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    costo_real = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    software_snapshot = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Software instalado (snapshot OCS)",
    )
    en_garantia = models.BooleanField(
        default=False,
        verbose_name="En garantía",
        help_text="Preventivo hecho mientras el equipo estaba en garantía: no cuenta como preventivo completo.",
    )
    formato = models.PositiveSmallIntegerField(default=FORMATO_ACTUAL, verbose_name="Formato")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_apertura", "-fecha_creacion"]
        verbose_name = "Orden de Mantenimiento"
        verbose_name_plural = "Ordenes de Mantenimiento"

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.activo.serial}"

    @property
    def checklist_items_completados(self):
        return self.checklist_items.filter(completado=True).count()


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


class ChecklistItem(models.Model):
    plan = models.ForeignKey(
        PlanMantenimiento,
        on_delete=models.CASCADE,
        related_name="checklist_items",
        null=True,
        blank=True,
        verbose_name="Plan (plantilla)",
    )
    orden = models.ForeignKey(
        OrdenMantenimiento,
        on_delete=models.CASCADE,
        related_name="checklist_items",
        null=True,
        blank=True,
        verbose_name="Orden (copia)",
    )
    descripcion = models.CharField(max_length=250)
    completado = models.BooleanField(default=False)
    posicion = models.PositiveIntegerField(default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["posicion", "id"]
        verbose_name = "Ítem de checklist"
        verbose_name_plural = "Ítems de checklist"

    def __str__(self):
        return self.descripcion


class FotoMantenimiento(models.Model):
    """Foto adicional de un mantenimiento (varias por orden)."""
    orden = models.ForeignKey(
        OrdenMantenimiento,
        on_delete=models.CASCADE,
        related_name="fotos",
    )
    foto = models.ImageField(upload_to="mantenimiento/fotos/", verbose_name="Foto")
    descripcion = models.CharField(max_length=200, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Foto de mantenimiento"
        verbose_name_plural = "Fotos de mantenimiento"

    def __str__(self):
        return self.descripcion or f"Foto #{self.pk}"


class PlantillaChecklist(models.Model):
    """Checklist de un preventivo. Hay uno por tipo de equipo.

    Los tipos que tienen plantilla son los que entran en la programación. Al
    iniciar un preventivo se copian a la orden los puntos activos; cambiar la
    plantilla después no toca las órdenes ya iniciadas.
    """

    # Sin choices a propósito (igual que Activo): también hay tipos creados a mano.
    tipo_dispositivo = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Tipo de equipo",
    )
    frecuencia_meses = models.PositiveSmallIntegerField(
        default=12,
        validators=[MinValueValidator(1)],
        verbose_name="Frecuencia (meses)",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tipo_dispositivo"]
        verbose_name = "Checklist"
        verbose_name_plural = "Checklists"

    def __str__(self):
        return f"Checklist · {self.get_tipo_dispositivo_display()}"

    def get_tipo_dispositivo_display(self):
        return _ver_tipo(self.tipo_dispositivo)


class PuntoPlantilla(models.Model):
    """Un punto de un checklist: sección, texto y si aplica en garantía."""

    plantilla = models.ForeignKey(
        PlantillaChecklist,
        on_delete=models.CASCADE,
        related_name="puntos",
    )
    seccion = models.CharField(max_length=60, verbose_name="Sección")
    descripcion = models.CharField(max_length=150, verbose_name="Descripción")
    posicion = models.PositiveIntegerField(default=0, verbose_name="Posición")
    aplica_en_garantia = models.BooleanField(default=False, verbose_name="Aplica en garantía")
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["posicion", "id"]
        verbose_name = "Punto de checklist"
        verbose_name_plural = "Puntos de checklist"

    def __str__(self):
        return f"{self.seccion} · {self.descripcion}"


class ProgramacionMantenimiento(models.Model):
    """Fecha en que se acordó hacerle el preventivo a un equipo.

    Es opcional: sin fila (o con la fecha vacía) el equipo se rige por la regla
    de "le toca desde" de ``mantenimiento.programacion``.
    """

    activo = models.OneToOneField(
        "inventario.Activo",
        on_delete=models.CASCADE,
        related_name="programacion_mantenimiento",
    )
    fecha_programada = models.DateField(null=True, blank=True, verbose_name="Fecha programada")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Programación de mantenimiento"
        verbose_name_plural = "Programaciones de mantenimiento"

    def __str__(self):
        return f"Programación · {self.activo.serial}"
