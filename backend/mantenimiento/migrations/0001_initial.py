from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("inventario", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlanMantenimiento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("preventivo", "Preventivo"), ("correctivo", "Correctivo")], max_length=20)),
                ("frecuencia_dias", models.PositiveIntegerField(blank=True, null=True)),
                ("fecha_inicio", models.DateField(blank=True, null=True)),
                ("proxima_ejecucion", models.DateField(blank=True, null=True)),
                ("estado", models.CharField(choices=[("activo", "Activo"), ("pausado", "Pausado")], default="activo", max_length=20)),
                ("responsable", models.CharField(blank=True, max_length=150)),
                ("observaciones", models.TextField(blank=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                ("activo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="planes_mantenimiento", to="inventario.activo")),
            ],
            options={
                "verbose_name": "Plan de Mantenimiento",
                "verbose_name_plural": "Planes de Mantenimiento",
                "ordering": ["-fecha_creacion"],
            },
        ),
        migrations.CreateModel(
            name="OrdenMantenimiento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("preventivo", "Preventivo"), ("correctivo", "Correctivo")], max_length=20)),
                ("estado", models.CharField(choices=[("abierta", "Abierta"), ("en_proceso", "En proceso"), ("cerrada", "Cerrada"), ("cancelada", "Cancelada")], default="abierta", max_length=20)),
                ("prioridad", models.CharField(choices=[("baja", "Baja"), ("media", "Media"), ("alta", "Alta")], default="media", max_length=20)),
                ("fecha_apertura", models.DateField(default=django.utils.timezone.now)),
                ("fecha_cierre", models.DateField(blank=True, null=True)),
                ("tecnico_asignado", models.CharField(blank=True, max_length=150)),
                ("descripcion", models.TextField(blank=True)),
                ("diagnostico", models.TextField(blank=True)),
                ("acciones", models.TextField(blank=True)),
                ("costo_estimado", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("costo_real", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                ("activo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ordenes_mantenimiento", to="inventario.activo")),
                ("plan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ordenes", to="mantenimiento.planmantenimiento")),
            ],
            options={
                "verbose_name": "Orden de Mantenimiento",
                "verbose_name_plural": "Ordenes de Mantenimiento",
                "ordering": ["-fecha_apertura", "-fecha_creacion"],
            },
        ),
        migrations.CreateModel(
            name="Repuesto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=150)),
                ("referencia", models.CharField(blank=True, max_length=120)),
                ("cantidad", models.PositiveIntegerField(default=1)),
                ("costo_unitario", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                ("orden", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="repuestos", to="mantenimiento.ordenmantenimiento")),
            ],
            options={
                "verbose_name": "Repuesto",
                "verbose_name_plural": "Repuestos",
                "ordering": ["nombre"],
            },
        ),
    ]
