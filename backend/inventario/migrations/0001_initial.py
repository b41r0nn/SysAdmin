import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("usuarios", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CatalogoModelo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_dispositivo", models.CharField(choices=[("celular", "Celular"), ("escritorio", "Equipo Escritorio"), ("portatil", "Portátil"), ("telefono_fijo", "Teléfono Fijo"), ("monitor", "Monitor")], max_length=50)),
                ("marca", models.CharField(max_length=100)),
                ("modelo", models.CharField(max_length=100)),
                ("especificaciones_json", models.JSONField(blank=True, default=dict)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Catálogo de Modelo", "verbose_name_plural": "Catálogo de Modelos", "ordering": ["tipo_dispositivo", "marca", "modelo"]},
        ),
        migrations.AddConstraint(
            model_name="catalogomodelo",
            constraint=models.UniqueConstraint(fields=("tipo_dispositivo", "marca", "modelo"), name="unique_catalogo_tipo_marca_modelo"),
        ),
        migrations.CreateModel(
            name="Activo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                # Comunes
                ("tipo_dispositivo", models.CharField(choices=[("celular", "Celular"), ("escritorio", "Equipo Escritorio"), ("portatil", "Portátil"), ("telefono_fijo", "Teléfono Fijo"), ("monitor", "Monitor")], max_length=50)),
                ("marca", models.CharField(max_length=100)),
                ("modelo", models.CharField(max_length=100)),
                ("serial", models.CharField(max_length=150, unique=True)),
                ("estado", models.CharField(choices=[("disponible", "Disponible"), ("asignado", "Asignado"), ("en_mantenimiento", "En mantenimiento"), ("en_reparacion", "En reparación"), ("dado_de_baja", "Dado de baja")], default="disponible", max_length=30)),
                ("ubicacion_fisica", models.CharField(blank=True, max_length=200)),
                ("fecha_compra", models.DateField(blank=True, null=True)),
                ("proveedor", models.CharField(blank=True, max_length=200)),
                ("valor_compra", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("garantia_fabrica_meses", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("garantia_extendida", models.BooleanField(default=False)),
                ("anios_garantia_extendida", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("foto_activo", models.ImageField(blank=True, null=True, upload_to="inventario/fotos/")),
                ("observaciones", models.TextField(blank=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                # Celular
                ("imei", models.CharField(blank=True, max_length=20, null=True, unique=True)),
                ("almacenamiento", models.CharField(blank=True, max_length=50)),
                ("ram_celular", models.CharField(blank=True, max_length=50)),
                ("procesador_celular", models.CharField(blank=True, max_length=100)),
                ("tipo_disco_celular", models.CharField(blank=True, max_length=50)),
                ("cuenta_correo_dispositivo", models.EmailField(blank=True)),
                ("numero_linea", models.CharField(blank=True, max_length=30)),
                ("operador", models.CharField(blank=True, max_length=100)),
                # Escritorio/Portátil
                ("disco_capacidad", models.CharField(blank=True, max_length=50)),
                ("tipo_disco", models.CharField(blank=True, max_length=50)),
                ("ram", models.CharField(blank=True, max_length=50)),
                ("procesador", models.CharField(blank=True, max_length=100)),
                ("sistema_operativo", models.CharField(blank=True, max_length=100)),
                ("licencia_so", models.CharField(blank=True, max_length=200)),
                ("usuario_red", models.CharField(blank=True, max_length=100)),
                ("usuario_admin_local", models.CharField(blank=True, max_length=100)),
                ("ip_equipo", models.GenericIPAddressField(blank=True, null=True)),
                ("mac_equipo", models.CharField(blank=True, max_length=17)),
                # Teléfono Fijo
                ("extension", models.CharField(blank=True, max_length=20)),
                ("puerto_jack", models.CharField(blank=True, max_length=50)),
                ("linea_asignada", models.CharField(blank=True, max_length=50)),
                # Monitor
                ("pulgadas", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
                ("resolucion", models.CharField(blank=True, max_length=50)),
                ("tipo_panel", models.CharField(blank=True, max_length=50)),
                ("conectores", models.CharField(blank=True, max_length=200)),
            ],
            options={"verbose_name": "Activo", "verbose_name_plural": "Activos", "ordering": ["-fecha_creacion"]},
        ),
        migrations.CreateModel(
            name="Asignacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("activo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="asignaciones", to="inventario.activo")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="asignaciones", to="usuarios.usuario")),
                ("fecha_asignacion", models.DateField()),
                ("fecha_devolucion", models.DateField(blank=True, null=True)),
                ("observaciones", models.TextField(blank=True)),
                ("activa", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Asignación", "verbose_name_plural": "Asignaciones", "ordering": ["-fecha_asignacion"]},
        ),
        migrations.CreateModel(
            name="Movimiento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("activo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movimientos", to="inventario.activo")),
                ("tipo", models.CharField(choices=[("ingreso", "Ingreso"), ("egreso", "Egreso"), ("traslado", "Traslado"), ("devolucion", "Devolución"), ("baja", "Baja")], max_length=20)),
                ("fecha", models.DateField()),
                ("descripcion", models.TextField(blank=True)),
                ("realizado_por", models.CharField(max_length=200)),
                ("usuario_destino", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="movimientos_destino", to="usuarios.usuario")),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Movimiento", "verbose_name_plural": "Movimientos", "ordering": ["-fecha", "-fecha_creacion"]},
        ),
        migrations.CreateModel(
            name="ActaAsignacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("asignacion", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="acta", to="inventario.asignacion")),
                ("fecha_generacion", models.DateTimeField(auto_now_add=True)),
                ("pdf_generado", models.FileField(upload_to="inventario/actas/pdf/")),
                ("escaneado_firmado", models.FileField(blank=True, null=True, upload_to="inventario/actas/firmadas/")),
                ("observaciones", models.TextField(blank=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Acta de Asignación", "verbose_name_plural": "Actas de Asignación"},
        ),
    ]
