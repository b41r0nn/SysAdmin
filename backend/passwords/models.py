from django.conf import settings
from django.db import models
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .crypto import build_fernet


ESTADOS_CREDENCIAL = [
    ("activa", "Activa"),
    ("expirada", "Expirada"),
    ("revocada", "Revocada"),
]


class Vault(models.Model):
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    acceso_requerido = models.BooleanField(default=False)
    acceso_hash = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vaults_creados",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Vault"
        verbose_name_plural = "Vaults"

    def __str__(self):
        return self.nombre

    def set_access_code(self, raw_code):
        if not raw_code:
            self.acceso_hash = ""
            return
        hasher = PasswordHasher()
        self.acceso_hash = hasher.hash(raw_code)

    def check_access_code(self, raw_code):
        if not self.acceso_requerido:
            return True
        if not self.acceso_hash or not raw_code:
            return False
        hasher = PasswordHasher()
        try:
            return hasher.verify(self.acceso_hash, raw_code)
        except VerifyMismatchError:
            return False


class Credencial(models.Model):
    vault = models.ForeignKey(Vault, on_delete=models.CASCADE, related_name="credenciales")
    titulo = models.CharField(max_length=150)
    usuario = models.CharField(max_length=150, blank=True)
    url = models.URLField(blank=True)
    secreto_encriptado = models.TextField(blank=True)
    notas = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS_CREDENCIAL, default="activa")
    fecha_expiracion = models.DateField(null=True, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credenciales_creadas",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_creacion"]
        verbose_name = "Credencial"
        verbose_name_plural = "Credenciales"

    def __str__(self):
        return f"{self.titulo} ({self.vault.nombre})"

    def set_secret(self, raw_secret):
        if raw_secret:
            fernet = build_fernet()
            token = fernet.encrypt(raw_secret.encode("utf-8"))
            self.secreto_encriptado = token.decode("utf-8")

    def get_secret(self):
        if not self.secreto_encriptado:
            return ""
        fernet = build_fernet()
        value = fernet.decrypt(self.secreto_encriptado.encode("utf-8"))
        return value.decode("utf-8")


class AccesoLog(models.Model):
    vault = models.ForeignKey(Vault, on_delete=models.CASCADE, related_name="logs")
    credencial = models.ForeignKey(
        Credencial,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    accion = models.CharField(max_length=50)
    detalle = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "Acceso log"
        verbose_name_plural = "Accesos log"

    def __str__(self):
        return f"{self.accion} · {self.vault.nombre}"
