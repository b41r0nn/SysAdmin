from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Vault",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120)),
                ("descripcion", models.TextField(blank=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                (
                    "creado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="vaults_creados",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Vault",
                "verbose_name_plural": "Vaults",
                "ordering": ["nombre"],
            },
        ),
        migrations.CreateModel(
            name="Credencial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=150)),
                ("usuario", models.CharField(blank=True, max_length=150)),
                ("url", models.URLField(blank=True)),
                ("secreto_encriptado", models.TextField(blank=True)),
                ("notas", models.TextField(blank=True)),
                ("estado", models.CharField(choices=[("activa", "Activa"), ("expirada", "Expirada"), ("revocada", "Revocada")], default="activa", max_length=20)),
                ("fecha_expiracion", models.DateField(blank=True, null=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                (
                    "creado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="credenciales_creadas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "vault",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="credenciales",
                        to="passwords.vault",
                    ),
                ),
            ],
            options={
                "verbose_name": "Credencial",
                "verbose_name_plural": "Credenciales",
                "ordering": ["-fecha_creacion"],
            },
        ),
    ]
