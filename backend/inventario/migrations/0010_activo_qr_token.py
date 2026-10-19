import uuid

from django.db import migrations, models


def generar_tokens(apps, schema_editor):
    Activo = apps.get_model("inventario", "Activo")
    for activo in Activo.objects.only("pk").iterator():
        Activo.objects.filter(pk=activo.pk).update(qr_token=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0009_softwareinstalado"),
    ]

    operations = [
        # Tres pasos: un default callable en AddField daría el mismo UUID a
        # todas las filas existentes y rompería el unique.
        migrations.AddField(
            model_name="activo",
            name="qr_token",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(generar_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="activo",
            name="qr_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
