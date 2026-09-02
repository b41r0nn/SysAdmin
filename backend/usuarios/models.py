from django.db import models


class Usuario(models.Model):
    ESTADO_CHOICES = [
        ("activo", "Activo"),
        ("inactivo", "Inactivo"),
    ]

    nombre_completo = models.CharField(max_length=200, verbose_name="Nombre completo")
    documento_identidad = models.CharField(
        max_length=50, unique=True, verbose_name="Documento de identidad"
    )
    cargo = models.CharField(max_length=150, verbose_name="Cargo")
    area = models.CharField(max_length=150, verbose_name="Área")
    correo = models.EmailField(verbose_name="Correo electrónico")
    telefono = models.CharField(max_length=50, blank=True, verbose_name="Teléfono")
    estado = models.CharField(
        max_length=10, choices=ESTADO_CHOICES, default="activo", verbose_name="Estado"
    )
    foto = models.ImageField(
        upload_to="usuarios/fotos/", blank=True, null=True, verbose_name="Foto"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    fecha_actualizacion = models.DateTimeField(auto_now=True, verbose_name="Fecha de actualización")

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        ordering = ["nombre_completo"]

    def __str__(self):
        return f"{self.nombre_completo} ({self.documento_identidad})"

    def desactivar(self):
        self.estado = "inactivo"
        self.save()

    def activar(self):
        self.estado = "activo"
        self.save()

    @property
    def is_activo(self):
        return self.estado == "activo"
