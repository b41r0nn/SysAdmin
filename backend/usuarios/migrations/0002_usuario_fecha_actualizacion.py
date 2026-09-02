from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="fecha_actualizacion",
            field=models.DateTimeField(auto_now=True, verbose_name="Fecha de actualización"),
        ),
    ]
