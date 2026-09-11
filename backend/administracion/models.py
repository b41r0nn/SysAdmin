from django.conf import settings
from django.db import models

from accounts.permisos import MODULOS
from passwords.crypto import build_fernet


MODULO_CHOICES = [
    (m, m.replace("_", " ").capitalize())
    for m in MODULOS
] + [("auth", "Inicio de sesión")]


class RegistroAuditoria(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_auditoria",
    )
    modulo = models.CharField(max_length=30, choices=MODULO_CHOICES)
    accion = models.CharField(max_length=30)
    objeto_tipo = models.CharField(max_length=60, blank=True, verbose_name="Tipo de objeto")
    objeto_id = models.PositiveBigIntegerField(null=True, blank=True, verbose_name="ID del objeto")
    detalle = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "Registro de auditoría"
        verbose_name_plural = "Registros de auditoría"
        indexes = [
            models.Index(fields=["modulo", "fecha"]),
            models.Index(fields=["usuario", "fecha"]),
        ]

    def __str__(self):
        return f"[{self.fecha:%Y-%m-%d %H:%M}] {self.usuario} · {self.modulo}/{self.accion}"


class ConfiguracionSistema(models.Model):
    nombre_empresa = models.CharField(
        max_length=150,
        default="REDIHOS S.A.S",
        verbose_name="Nombre de la empresa",
    )
    nit = models.CharField(max_length=20, blank=True, verbose_name="NIT")
    direccion = models.CharField(max_length=200, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    email_contacto = models.EmailField(blank=True, verbose_name="Correo de contacto")
    pie_firma_reporte = models.CharField(
        max_length=200,
        blank=True,
        default="Departamento de Sistemas",
        verbose_name="Firma de reportes",
    )
    smtp_host = models.CharField(max_length=150, blank=True, verbose_name="Servidor SMTP")
    smtp_puerto = models.PositiveIntegerField(default=587, verbose_name="Puerto SMTP")
    smtp_usuario = models.CharField(max_length=150, blank=True, verbose_name="Usuario SMTP")
    smtp_password_cifrado = models.TextField(blank=True, verbose_name="Contraseña SMTP")
    smtp_usa_tls = models.BooleanField(default=True, verbose_name="Usar STARTTLS")
    smtp_usa_ssl = models.BooleanField(default=False, verbose_name="Usar SSL")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración del sistema"
        verbose_name_plural = "Configuración del sistema"

    def __str__(self):
        return self.nombre_empresa

    @classmethod
    def get_config(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def set_smtp_password(self, raw):
        """Cifra la contraseña SMTP con Fernet y la guarda."""
        self.smtp_password_cifrado = build_fernet().encrypt(raw.encode()).decode()

    def get_smtp_password(self):
        """Devuelve la contraseña SMTP descifrada (o cadena vacía)."""
        if not self.smtp_password_cifrado:
            return ""
        return build_fernet().decrypt(self.smtp_password_cifrado.encode()).decode()