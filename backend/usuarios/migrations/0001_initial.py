from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Usuario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre_completo", models.CharField(max_length=200, verbose_name="Nombre completo")),
                ("documento_identidad", models.CharField(max_length=50, unique=True, verbose_name="Documento de identidad")),
                ("cargo", models.CharField(max_length=150, verbose_name="Cargo")),
                ("area", models.CharField(max_length=150, verbose_name="Área")),
                ("correo", models.EmailField(verbose_name="Correo electrónico")),
                ("telefono", models.CharField(blank=True, max_length=50, verbose_name="Teléfono")),
                ("estado", models.CharField(
                    choices=[("activo", "Activo"), ("inactivo", "Inactivo")],
                    default="activo",
                    max_length=10,
                    verbose_name="Estado",
                )),
                ("foto", models.ImageField(blank=True, null=True, upload_to="usuarios/fotos/", verbose_name="Foto")),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")),
            ],
            options={
                "verbose_name": "Usuario",
                "verbose_name_plural": "Usuarios",
                "ordering": ["nombre_completo"],
            },
        ),
    ]
