from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("passwords", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="vault",
            name="acceso_requerido",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="vault",
            name="acceso_hash",
            field=models.TextField(blank=True),
        ),
    ]