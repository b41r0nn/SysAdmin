from django.db import migrations, models


def copiar_tipo_desde_activo(apps, schema_editor):
    PlanMantenimiento = apps.get_model("mantenimiento", "PlanMantenimiento")
    for plan in PlanMantenimiento.objects.select_related("activo").iterator():
        plan.tipo_dispositivo = plan.activo.tipo_dispositivo if plan.activo_id else ""
        plan.save(update_fields=["tipo_dispositivo"])


class Migration(migrations.Migration):

    dependencies = [
        ("mantenimiento", "0006_ordenmantenimiento_software_snapshot_and_more"),
        ("inventario", "0007_alter_activo_tipo_dispositivo_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="planmantenimiento",
            name="tipo_dispositivo",
            field=models.CharField(default="", max_length=50, verbose_name="Categoría de equipo"),
            preserve_default=False,
        ),
        migrations.RunPython(copiar_tipo_desde_activo, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="planmantenimiento",
            name="activo",
        ),
    ]