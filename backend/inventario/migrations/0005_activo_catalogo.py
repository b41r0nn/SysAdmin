from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0004_activo_nombre_equipo'),
    ]

    operations = [
        migrations.AddField(
            model_name='activo',
            name='catalogo',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='activos',
                to='inventario.catalogomodelo',
                verbose_name='Catálogo / Modelo',
            ),
        ),
    ]
