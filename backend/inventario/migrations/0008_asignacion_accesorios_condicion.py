from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0007_alter_activo_tipo_dispositivo_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="asignacion",
            name="accesorios",
            field=models.TextField(
                blank=True,
                help_text="Ej: cargador, mouse, maletín, base…",
                verbose_name="Accesorios entregados",
            ),
        ),
        migrations.AddField(
            model_name="asignacion",
            name="condicion_entrega",
            field=models.CharField(
                blank=True,
                default="Nuevo",
                help_text="Ej: nuevo, usado en buen estado…",
                max_length=200,
                verbose_name="Condición de entrega",
            ),
        ),
    ]