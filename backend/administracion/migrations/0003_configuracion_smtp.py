from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("administracion", "0002_alter_registroauditoria_modulo"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracionsistema",
            name="smtp_host",
            field=models.CharField(blank=True, max_length=150, verbose_name="Servidor SMTP"),
        ),
        migrations.AddField(
            model_name="configuracionsistema",
            name="smtp_password_cifrado",
            field=models.TextField(blank=True, verbose_name="Contraseña SMTP"),
        ),
        migrations.AddField(
            model_name="configuracionsistema",
            name="smtp_puerto",
            field=models.PositiveIntegerField(default=587, verbose_name="Puerto SMTP"),
        ),
        migrations.AddField(
            model_name="configuracionsistema",
            name="smtp_usa_ssl",
            field=models.BooleanField(default=False, verbose_name="Usar SSL"),
        ),
        migrations.AddField(
            model_name="configuracionsistema",
            name="smtp_usa_tls",
            field=models.BooleanField(default=True, verbose_name="Usar STARTTLS"),
        ),
        migrations.AddField(
            model_name="configuracionsistema",
            name="smtp_usuario",
            field=models.CharField(blank=True, max_length=150, verbose_name="Usuario SMTP"),
        ),
    ]