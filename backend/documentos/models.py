from django.conf import settings
from django.db import models


TIPOS_DOCUMENTO = [
    ("manual", "Manual"),
    ("procedimiento", "Procedimiento"),
    ("politica", "Política"),
    ("general", "Documento general"),
]


class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

    def __str__(self):
        return self.nombre


class Documento(models.Model):
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name="documentos",
        null=True,
        blank=True,
    )
    tipo_documento = models.CharField(
        max_length=30,
        choices=TIPOS_DOCUMENTO,
        default="general",
        verbose_name="Tipo de documento",
    )
    archivo = models.FileField(upload_to="documentos/%Y/%m/")
    version = models.CharField(max_length=20, blank=True, verbose_name="Versión")
    fecha_version = models.DateField(null=True, blank=True, verbose_name="Fecha de versión")
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documentos_subidos",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_actualizacion"]
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"

    def __str__(self):
        return self.titulo

    @property
    def extension(self):
        if self.archivo:
            nombre = self.archivo.name
            if "." in nombre:
                return nombre.rsplit(".", 1)[1].lower()
        return ""

    @property
    def icono_tipo(self):
        ext = self.extension
        if ext in {"pdf"}:
            return "bi-filetype-pdf"
        if ext in {"doc", "docx"}:
            return "bi-filetype-doc"
        if ext in {"xls", "xlsx"}:
            return "bi-filetype-xls"
        if ext in {"ppt", "pptx"}:
            return "bi-filetype-ppt"
        if ext in {"zip", "rar", "7z"}:
            return "bi-file-zip"
        return "bi-file-earmark"
