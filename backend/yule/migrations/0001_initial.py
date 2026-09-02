# Generated migration for Yule models - 7B Synchronization

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventario', '0001_initial'),  # Adjust to match your actual migration
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionYule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(default='Configuración OCS', max_length=100, unique=True)),
                ('ultima_sincronizacion', models.DateTimeField(blank=True, null=True)),
                ('frecuencia_sync_minutos', models.PositiveIntegerField(default=60)),
                ('auto_sync_habilitado', models.BooleanField(default=False)),
                ('descripcion', models.TextField(blank=True)),
                ('activa', models.BooleanField(default=True)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('creada_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='configs_yule', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Configuración Yule',
                'verbose_name_plural': 'Configuraciones Yule',
            },
        ),
        migrations.CreateModel(
            name='SincronizacionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estado', models.CharField(choices=[('exitosa', 'Exitosa'), ('fallo', 'Fallo'), ('parcial', 'Parcial')], default='exitosa', max_length=20)),
                ('equipos_detectados', models.PositiveIntegerField(default=0)),
                ('equipos_nuevos', models.PositiveIntegerField(default=0)),
                ('equipos_actualizados', models.PositiveIntegerField(default=0)),
                ('equipos_desaparecidos', models.PositiveIntegerField(default=0)),
                ('mensaje_error', models.TextField(blank=True)),
                ('detalles_json', models.JSONField(blank=True, default=dict)),
                ('duracion_segundos', models.PositiveIntegerField(blank=True, null=True)),
                ('fecha_inicio', models.DateTimeField(auto_now_add=True)),
                ('fecha_fin', models.DateTimeField(blank=True, null=True)),
                ('realizado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sincronizaciones_yule', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Sincronización Yule',
                'verbose_name_plural': 'Sincronizaciones Yule',
                'ordering': ['-fecha_inicio'],
            },
        ),
        migrations.CreateModel(
            name='EquipoOCS',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('id_ocs', models.CharField(db_index=True, max_length=50, unique=True)),
                ('tipo_dispositivo', models.CharField(choices=[('computadora', 'Computadora'), ('impresora', 'Impresora'), ('servidor', 'Servidor'), ('red', 'Dispositivo Red'), ('otro', 'Otro')], default='computadora', max_length=50)),
                ('nombre_host', models.CharField(db_index=True, max_length=255)),
                ('usuario_dominio', models.CharField(blank=True, max_length=255)),
                ('so_nombre', models.CharField(blank=True, max_length=255)),
                ('so_version', models.CharField(blank=True, max_length=255)),
                ('procesador', models.CharField(blank=True, max_length=255)),
                ('memoria_ram_mb', models.PositiveIntegerField(blank=True, null=True)),
                ('almacenamiento_total_gb', models.PositiveIntegerField(blank=True, null=True)),
                ('serial_bios', models.CharField(blank=True, max_length=255)),
                ('mac_address', models.CharField(blank=True, db_index=True, max_length=50)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('ultimo_reporte_ocs', models.DateTimeField(blank=True, null=True)),
                ('visto_en_ultima_sync', models.BooleanField(default=True)),
                ('observaciones', models.TextField(blank=True)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('fecha_primera_deteccion', models.DateTimeField(default=django.utils.timezone.now)),
                ('activo_local', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='equipo_ocs', to='inventario.activo')),
            ],
            options={
                'verbose_name': 'Equipo OCS',
                'verbose_name_plural': 'Equipos OCS',
                'ordering': ['-ultimo_reporte_ocs'],
            },
        ),
        migrations.AddIndex(
            model_name='equipoocs',
            index=models.Index(fields=['id_ocs'], name='yule_equipo_id_ocs_idx'),
        ),
        migrations.AddIndex(
            model_name='equipoocs',
            index=models.Index(fields=['nombre_host'], name='yule_equipo_nombre_host_idx'),
        ),
        migrations.AddIndex(
            model_name='equipoocs',
            index=models.Index(fields=['mac_address'], name='yule_equipo_mac_address_idx'),
        ),
        migrations.AddIndex(
            model_name='equipoocs',
            index=models.Index(fields=['activo_local'], name='yule_equipo_activo_local_idx'),
        ),
    ]
