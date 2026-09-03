from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0003_alter_movimiento_tipo'),
    ]

    operations = [
        migrations.AddField(
            model_name='activo',
            name='nombre_equipo',
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
