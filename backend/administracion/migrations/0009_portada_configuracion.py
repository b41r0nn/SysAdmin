from django.db import migrations

ANTES = "administracion:lista_auditoria"
DESPUES = "administracion:inicio"


def apuntar_a_la_portada(apps, schema_editor):
    Modulo = apps.get_model("administracion", "Modulo")
    Modulo.objects.filter(clave="administracion").update(url_nombre=DESPUES)


def volver_a_la_auditoria(apps, schema_editor):
    Modulo = apps.get_model("administracion", "Modulo")
    Modulo.objects.filter(clave="administracion").update(url_nombre=ANTES)


class Migration(migrations.Migration):

    dependencies = [
        ("administracion", "0008_sembrar_roles_permisos"),
    ]

    operations = [
        migrations.RunPython(apuntar_a_la_portada, volver_a_la_auditoria),
    ]
