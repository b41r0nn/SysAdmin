from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mantenimiento", "0004_add_reportado_por"),
    ]

    operations = [
        migrations.AddField(
            model_name="ordenmantenimiento",
            name="foto",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="mantenimiento/fotos/",
                verbose_name="Foto del problema",
            ),
        ),
    ]