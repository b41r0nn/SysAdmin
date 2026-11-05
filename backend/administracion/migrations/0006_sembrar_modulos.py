from django.db import migrations

# (clave, nombre, icono, url_nombre, orden, activo, es_esencial)
# Copia congelada: la migración no importa nada de la aplicación para seguir
# siendo válida aunque el catálogo cambie después.
MODULOS_INICIALES = [
    ("usuarios", "Usuarios", "bi-people", "usuarios:lista", 10, True, False),
    ("inventario", "Inventario", "bi-laptop", "inventario:lista", 20, True, True),
    ("reportes", "Reportes", "bi-file-earmark-bar-graph", "reports:index", 30, True, False),
    ("mantenimiento", "Mantenimiento", "bi-tools", "mantenimiento:inicio", 40, True, True),
    ("licencias", "Licencias", "bi-diamond", "licencias:lista", 50, False, False),
    ("prestamos", "Préstamos", "bi-box-arrow-in-right", "prestamos:lista", 60, False, False),
    ("documentos", "Documentos", "bi-folder", "documentos:lista", 70, True, False),
    ("soporte", "Soporte", "bi-life-preserver", "soporte:lista", 80, True, False),
    ("passwords", "Contraseñas", "bi-key", "passwords:index", 90, True, True),
    # La URL definitiva (administracion:inicio) llega con la pantalla de
    # configuración; mientras tanto se apunta a una que ya existe.
    ("administracion", "Configuración", "bi-shield-lock", "administracion:lista_auditoria", 100, True, True),
]


def sembrar_modulos(apps, schema_editor):
    Modulo = apps.get_model("administracion", "Modulo")
    for clave, nombre, icono, url_nombre, orden, activo, es_esencial in MODULOS_INICIALES:
        Modulo.objects.get_or_create(
            clave=clave,
            defaults={
                "nombre": nombre,
                "icono": icono,
                "url_nombre": url_nombre,
                "orden": orden,
                "activo": activo,
                "es_esencial": es_esencial,
            },
        )


def quitar_modulos(apps, schema_editor):
    Modulo = apps.get_model("administracion", "Modulo")
    Modulo.objects.filter(clave__in=[fila[0] for fila in MODULOS_INICIALES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("administracion", "0005_modulo"),
    ]

    operations = [
        migrations.RunPython(sembrar_modulos, quitar_modulos),
    ]
