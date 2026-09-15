import calendar
from datetime import date

from django.db import models
from django.db.models import Max
from django.utils import timezone


def _add_months(d, months):
    """Add months to a date without dateutil dependency."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


TIPOS = [
    ("celular", "Celular"),
    ("escritorio", "Equipo Escritorio"),
    ("portatil", "Portátil"),
    ("telefono_fijo", "Teléfono Fijo"),
    ("monitor", "Monitor"),
]

ESTADOS = [
    ("disponible", "Disponible"),
    ("asignado", "Asignado"),
    ("en_mantenimiento", "En mantenimiento"),
    ("en_reparacion", "En reparación"),
    ("dado_de_baja", "Dado de baja"),
]

NUMERO_INTERNO_INICIO = 1000


def _siguiente_numero_interno():
    ultimo = Activo.objects.exclude(numero_interno__isnull=True).aggregate(
        Max("numero_interno")
    )["numero_interno__max"]
    return (ultimo or NUMERO_INTERNO_INICIO - 1) + 1


def _ver_tipo(tipo):
    """Devuelve el nombre legible de un tipo de dispositivo.
    Si el tipo fue creado a mano (no está en TIPOS), devuelve el valor crudo."""
    return dict(TIPOS).get(tipo, tipo)


class CatalogoModelo(models.Model):
    # Sin choices a nivel modelo a propósito: el usuario puede crear tipos
    # nuevos desde el formulario. TIPOS solo se usa para el menú y display.
    tipo_dispositivo = models.CharField(max_length=50)
    marca = models.CharField(max_length=100)
    modelo = models.CharField(max_length=100)
    especificaciones_json = models.JSONField(default=dict, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tipo_dispositivo", "marca", "modelo"]
        verbose_name = "Catálogo de Modelo"
        verbose_name_plural = "Catálogo de Modelos"
        unique_together = ("tipo_dispositivo", "marca", "modelo")

    def get_tipo_dispositivo_display(self):
        return _ver_tipo(self.tipo_dispositivo)

    def __str__(self):
        return f"{self.get_tipo_dispositivo_display()} — {self.marca} {self.modelo}"


class Activo(models.Model):
    # ── Comunes ──────────────────────────────────────────────────────────────
    tipo_dispositivo = models.CharField(max_length=50)
    catalogo = models.ForeignKey(
        CatalogoModelo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activos",
        verbose_name="Catálogo / Modelo",
    )
    marca = models.CharField(max_length=100)
    modelo = models.CharField(max_length=100)
    serial = models.CharField(max_length=150, unique=True)
    numero_interno = models.PositiveIntegerField(unique=True, editable=False, null=True, blank=True)
    estado = models.CharField(max_length=30, choices=ESTADOS, default="disponible")
    ubicacion_fisica = models.CharField(max_length=200, blank=True)
    fecha_compra = models.DateField(null=True, blank=True)
    proveedor = models.CharField(max_length=200, blank=True)
    valor_compra = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    garantia_fabrica_meses = models.PositiveSmallIntegerField(null=True, blank=True)
    garantia_extendida = models.BooleanField(default=False)
    anios_garantia_extendida = models.PositiveSmallIntegerField(null=True, blank=True)
    foto_activo = models.ImageField(upload_to="inventario/fotos/", null=True, blank=True)
    observaciones = models.TextField(blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    # ── Celular ───────────────────────────────────────────────────────────────
    imei = models.CharField(max_length=20, unique=True, null=True, blank=True)
    almacenamiento = models.CharField(max_length=50, blank=True)
    ram_celular = models.CharField(max_length=50, blank=True)
    procesador_celular = models.CharField(max_length=100, blank=True)
    tipo_disco_celular = models.CharField(max_length=50, blank=True)
    cuenta_correo_dispositivo = models.EmailField(blank=True)
    numero_linea = models.CharField(max_length=30, blank=True)
    operador = models.CharField(max_length=100, blank=True)

    # ── Escritorio / Portátil ─────────────────────────────────────────────────
    nombre_equipo = models.CharField(max_length=150, blank=True)
    disco_capacidad = models.CharField(max_length=50, blank=True)
    tipo_disco = models.CharField(max_length=50, blank=True)
    ram = models.CharField(max_length=50, blank=True)
    procesador = models.CharField(max_length=100, blank=True)
    sistema_operativo = models.CharField(max_length=100, blank=True)
    licencia_so = models.CharField(max_length=200, blank=True)
    usuario_red = models.CharField(max_length=100, blank=True)
    usuario_admin_local = models.CharField(max_length=100, blank=True)
    ip_equipo = models.GenericIPAddressField(null=True, blank=True)
    mac_equipo = models.CharField(max_length=17, blank=True)  # XX:XX:XX:XX:XX:XX

    # ── Teléfono Fijo ─────────────────────────────────────────────────────────
    extension = models.CharField(max_length=20, blank=True)
    puerto_jack = models.CharField(max_length=50, blank=True)
    linea_asignada = models.CharField(max_length=50, blank=True)

    # ── Monitor ───────────────────────────────────────────────────────────────
    pulgadas = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    resolucion = models.CharField(max_length=50, blank=True)
    tipo_panel = models.CharField(max_length=50, blank=True)
    conectores = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Activo"
        verbose_name_plural = "Activos"

    def get_tipo_dispositivo_display(self):
        return _ver_tipo(self.tipo_dispositivo)

    def __str__(self):
        return f"[{self.get_tipo_dispositivo_display()}] {self.marca} {self.modelo} — {self.serial}"

    def save(self, *args, **kwargs):
        if self.numero_interno is None:
            self.numero_interno = _siguiente_numero_interno()
        super().save(*args, **kwargs)

    # ── Properties ───────────────────────────────────────────────────────────
    @property
    def fecha_vencimiento_garantia(self):
        if not self.fecha_compra or not self.garantia_fabrica_meses:
            return None
        meses = self.garantia_fabrica_meses
        if self.garantia_extendida and self.anios_garantia_extendida:
            meses += self.anios_garantia_extendida * 12
        return _add_months(self.fecha_compra, meses)

    @property
    def en_garantia(self):
        venc = self.fecha_vencimiento_garantia
        if venc is None:
            return False
        return timezone.now().date() <= venc


class Asignacion(models.Model):
    activo = models.ForeignKey(
        Activo, on_delete=models.PROTECT, related_name="asignaciones"
    )
    usuario = models.ForeignKey(
        "usuarios.Usuario", on_delete=models.PROTECT, related_name="asignaciones"
    )
    fecha_asignacion = models.DateField()
    fecha_devolucion = models.DateField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    accesorios = models.TextField(
        blank=True,
        verbose_name="Accesorios entregados",
        help_text="Ej: cargador, mouse, maletín, base…",
    )
    condicion_entrega = models.CharField(
        max_length=200,
        blank=True,
        default="Nuevo",
        verbose_name="Condición de entrega",
        help_text="Ej: nuevo, usado en buen estado…",
    )
    activa = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_asignacion"]
        verbose_name = "Asignación"
        verbose_name_plural = "Asignaciones"

    def __str__(self):
        return f"{self.activo} → {self.usuario} ({self.fecha_asignacion})"


TIPOS_MOVIMIENTO = [
    ("ingreso", "Ingreso"),
    ("egreso", "Egreso"),
    ("traslado", "Traslado"),
    ("devolucion", "Devolución"),
    ("baja", "Baja"),
    ("asignacion", "Asignación"),
]


class Movimiento(models.Model):
    activo = models.ForeignKey(
        Activo, on_delete=models.PROTECT, related_name="movimientos"
    )
    tipo = models.CharField(max_length=20, choices=TIPOS_MOVIMIENTO)
    fecha = models.DateField()
    descripcion = models.TextField(blank=True)
    realizado_por = models.CharField(max_length=200)
    usuario_destino = models.ForeignKey(
        "usuarios.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_destino",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha", "-fecha_creacion"]
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos"

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.activo} ({self.fecha})"


class ActaAsignacion(models.Model):
    asignacion = models.OneToOneField(
        Asignacion, on_delete=models.PROTECT, related_name="acta"
    )
    fecha_generacion = models.DateTimeField(auto_now_add=True)
    pdf_generado = models.FileField(upload_to="inventario/actas/pdf/", null=True, blank=True)
    escaneado_firmado = models.FileField(
        upload_to="inventario/actas/firmadas/", null=True, blank=True
    )
    observaciones = models.TextField(blank=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Acta de Asignación"
        verbose_name_plural = "Actas de Asignación"

    def __str__(self):
        return f"Acta #{self.pk} — {self.asignacion}"
