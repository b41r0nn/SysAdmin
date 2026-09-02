from django.db import models
from django.conf import settings
from django.utils import timezone


TIPOS_DISPOSITIVO_OCS = [
    ("computadora", "Computadora"),
    ("impresora", "Impresora"),
    ("servidor", "Servidor"),
    ("red", "Dispositivo Red"),
    ("otro", "Otro"),
]

ESTADOS_SINCRONIZACION = [
    ("exitosa", "Exitosa"),
    ("fallo", "Fallo"),
    ("parcial", "Parcial"),
]


class ConfiguracionYule(models.Model):
    """Configuración global de Yule (OCS)"""
    nombre = models.CharField(max_length=100, default="Configuración OCS", unique=True)
    ultima_sincronizacion = models.DateTimeField(null=True, blank=True)
    frecuencia_sync_minutos = models.PositiveIntegerField(default=60)
    auto_sync_habilitado = models.BooleanField(default=False)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configs_yule",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración Yule"
        verbose_name_plural = "Configuraciones Yule"

    def __str__(self):
        return self.nombre


class EquipoOCS(models.Model):
    """Equipo detectado en OCS/Inventory NG"""
    # IDs de OCS
    id_ocs = models.CharField(max_length=50, unique=True, db_index=True)
    tipo_dispositivo = models.CharField(max_length=50, choices=TIPOS_DISPOSITIVO_OCS, default="computadora")
    
    # Información del sistema
    nombre_host = models.CharField(max_length=255, db_index=True)
    usuario_dominio = models.CharField(max_length=255, blank=True)
    so_nombre = models.CharField(max_length=255, blank=True)
    so_version = models.CharField(max_length=255, blank=True)
    
    # Hardware
    procesador = models.CharField(max_length=255, blank=True)
    memoria_ram_mb = models.PositiveIntegerField(null=True, blank=True)
    almacenamiento_total_gb = models.PositiveIntegerField(null=True, blank=True)
    
    # Identificadores
    serial_bios = models.CharField(max_length=255, blank=True)
    mac_address = models.CharField(max_length=50, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Inventario local
    activo_local = models.ForeignKey(
        "inventario.Activo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="equipo_ocs",
    )
    
    # Información de sincronización
    ultimo_reporte_ocs = models.DateTimeField(null=True, blank=True)
    visto_en_ultima_sync = models.BooleanField(default=True)
    
    # Notas
    observaciones = models.TextField(blank=True)
    
    # Timestamps
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    fecha_primera_deteccion = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-ultimo_reporte_ocs"]
        verbose_name = "Equipo OCS"
        verbose_name_plural = "Equipos OCS"
        indexes = [
            models.Index(fields=["id_ocs"]),
            models.Index(fields=["nombre_host"]),
            models.Index(fields=["mac_address"]),
            models.Index(fields=["activo_local"]),
        ]

    def __str__(self):
        return f"{self.nombre_host} ({self.id_ocs})"

    @property
    def esta_vinculado(self):
        return self.activo_local_id is not None

    @property
    def dias_sin_reporte(self):
        if not self.ultimo_reporte_ocs:
            return None
        return (timezone.now() - self.ultimo_reporte_ocs).days


class SincronizacionLog(models.Model):
    """Log de cada sincronización con OCS"""
    estado = models.CharField(max_length=20, choices=ESTADOS_SINCRONIZACION, default="exitosa")
    equipos_detectados = models.PositiveIntegerField(default=0)
    equipos_nuevos = models.PositiveIntegerField(default=0)
    equipos_actualizados = models.PositiveIntegerField(default=0)
    equipos_desaparecidos = models.PositiveIntegerField(default=0)
    
    # Errores
    mensaje_error = models.TextField(blank=True)
    detalles_json = models.JSONField(default=dict, blank=True)
    
    # Realizado por
    realizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sincronizaciones_yule",
    )
    
    # Duracion
    duracion_segundos = models.PositiveIntegerField(null=True, blank=True)
    
    # Timestamps
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha_inicio"]
        verbose_name = "Sincronización Yule"
        verbose_name_plural = "Sincronizaciones Yule"

    def __str__(self):
        return f"Sync {self.fecha_inicio.strftime('%Y-%m-%d %H:%M')} — {self.estado}"

    @property
    def fue_exitosa(self):
        return self.estado == "exitosa"
