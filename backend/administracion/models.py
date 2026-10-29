from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from accounts.permisos import MODULOS
from passwords.crypto import build_fernet


# Módulos sobre los que se conceden permisos. La auditoría añade "auth" porque
# el inicio de sesión también se registra, pero no es un módulo con permisos.
MODULO_CHOICES_PERMISOS = [
    (m, m.replace("_", " ").capitalize())
    for m in MODULOS
]

MODULO_CHOICES = MODULO_CHOICES_PERMISOS + [("auth", "Inicio de sesión")]


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
    # Encabezado y pie del acta de mantenimiento; vacíos, el acta muestra "—".
    acta_mant_codigo = models.CharField("Código del acta de mantenimiento", max_length=30, blank=True)
    acta_mant_version = models.CharField("Versión del acta de mantenimiento", max_length=10, blank=True)
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


class Modulo(models.Model):
    """Catálogo de módulos de la aplicación.

    Es la fuente de verdad de qué módulos están encendidos y de cómo se pintan
    en el menú. Las claves son las de ``accounts.permisos.MODULOS``.
    """

    clave = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=60)
    icono = models.CharField(
        max_length=60,
        help_text="Clase de bootstrap-icons, por ejemplo bi-laptop.",
    )
    url_nombre = models.CharField(
        max_length=100,
        verbose_name="Nombre de la URL",
        help_text="Nombre con namespace que acepta reverse(), por ejemplo inventario:lista.",
    )
    orden = models.PositiveIntegerField()
    activo = models.BooleanField(default=True)
    es_esencial = models.BooleanField(
        default=False,
        verbose_name="Es esencial",
        help_text="Un módulo esencial no se puede desactivar.",
    )

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "Módulo"
        verbose_name_plural = "Módulos"

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()
        if self.es_esencial and not self.activo:
            raise ValidationError(
                {"activo": f"El módulo «{self.nombre}» es esencial y no se puede desactivar."}
            )

    def save(self, *args, **kwargs):
        # La regla vive en el modelo y no en un formulario: una validación que
        # solo está en el HTML no es una validación.
        self.full_clean()
        super().save(*args, **kwargs)


class Rol(models.Model):
    """Catálogo de roles de usuario.

    Las claves son las que guarda ``CustomUser.rol``, que sigue siendo un
    ``CharField``: esta tabla manda en los ``choices`` del campo, no en su tipo.
    """

    clave = models.CharField(max_length=20, unique=True)  # el largo de CustomUser.rol
    nombre = models.CharField(max_length=60)
    es_sistema = models.BooleanField(
        default=False,
        verbose_name="Es de sistema",
        help_text="Un rol de sistema no se puede borrar.",
    )
    orden = models.PositiveIntegerField()

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "Rol"
        verbose_name_plural = "Roles"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        # La validación vive en el modelo y no en un formulario: sin
        # full_clean() una clave vacía llegaría a la tabla y, de ahí, a los
        # choices de CustomUser.rol.
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # La regla vive en el modelo y no en un formulario. Se lanza
        # ValidationError, y no ProtectedError, por coherencia con Modulo.
        if self.es_sistema:
            raise ValidationError(
                f"El rol «{self.nombre}» es de sistema y no se puede borrar."
            )
        return super().delete(*args, **kwargs)


class PermisoRol(models.Model):
    """Una celda de la matriz de permisos: qué puede hacer un rol en un módulo.

    Se lee siempre por ``accounts.permisos.nivel_permiso``, nunca directamente.
    """

    NIVEL_CHOICES = [
        ("ninguno", "Ninguno"),
        ("lectura", "Lectura"),
        ("escritura", "Escritura"),
    ]

    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name="permisos")
    modulo = models.CharField(
        max_length=30,
        choices=MODULO_CHOICES_PERMISOS,
        verbose_name="Módulo",
    )
    nivel = models.CharField(max_length=10, choices=NIVEL_CHOICES, default="ninguno")

    class Meta:
        unique_together = ("rol", "modulo")
        ordering = ["rol", "modulo"]
        verbose_name = "Permiso de rol"
        verbose_name_plural = "Permisos de rol"

    def __str__(self):
        return f"{self.rol.clave}/{self.modulo} = {self.nivel}"

    def save(self, *args, **kwargs):
        # Sin full_clean() un nivel fuera de NIVEL_CHOICES (p. ej. "admin") se
        # guardaría, y tiene_permiso() lo trataría como una lectura concedida.
        self.full_clean()
        super().save(*args, **kwargs)
