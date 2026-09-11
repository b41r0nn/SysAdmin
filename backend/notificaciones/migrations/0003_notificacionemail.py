from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notificaciones", "0002_alter_notificacion_tipo"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificacionEmail",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("destinatario", models.EmailField()),
                ("asunto", models.CharField(max_length=200)),
                ("cuerpo", models.TextField()),
                ("adjunto_tipo", models.CharField(blank=True, default="", max_length=30)),
                ("adjunto_objeto_id", models.PositiveIntegerField(blank=True, null=True)),
                ("enviado", models.BooleanField(default=False)),
                ("intentos", models.PositiveIntegerField(default=0)),
                ("error", models.TextField(blank=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_enviado", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["fecha_creacion"],
                "verbose_name": "Notificación email",
                "verbose_name_plural": "Notificaciones email",
            },
        ),
        migrations.AddIndex(
            model_name="notificacionemail",
            index=models.Index(fields=["enviado", "intentos"], name="notificacio_enviado_781966_idx"),
        ),
    ]