from django.db import migrations

# (clave, nombre, orden). Los nombres son los de CustomUser.ROL_CHOICES. Los
# cuatro son de sistema: borrar uno dejaría cuentas con un rol inexistente.
ROLES_INICIALES = [
    ("superadmin", "Super Administrador", 10),
    ("admin", "Administrador", 20),
    ("tecnico", "Técnico", 30),
    ("lectura", "Solo lectura", 40),
]

# {rol: {módulo: nivel}}: las 40 celdas de fábrica. Copia congelada de la
# matriz que tenía el código al escribir esta migración: no importa nada de la
# aplicación, para que `migrate` sobre una base nueva siga corriendo igual
# aunque esa matriz cambie o desaparezca después.
PERMISOS_INICIALES = {
    "superadmin": {
        "usuarios": "escritura",
        "inventario": "escritura",
        "mantenimiento": "escritura",
        "passwords": "escritura",
        "reportes": "escritura",
        "documentos": "escritura",
        "administracion": "escritura",
        "soporte": "escritura",
        "licencias": "escritura",
        "prestamos": "escritura",
    },
    "admin": {
        "usuarios": "escritura",
        "inventario": "escritura",
        "mantenimiento": "escritura",
        "passwords": "lectura",
        "reportes": "escritura",
        "documentos": "escritura",
        "administracion": "ninguno",
        "soporte": "escritura",
        "licencias": "escritura",
        "prestamos": "escritura",
    },
    "tecnico": {
        "usuarios": "lectura",
        "inventario": "escritura",
        "mantenimiento": "escritura",
        "passwords": "ninguno",
        "reportes": "lectura",
        "documentos": "lectura",
        "administracion": "ninguno",
        "soporte": "escritura",
        "licencias": "lectura",
        "prestamos": "escritura",
    },
    "lectura": {
        "usuarios": "lectura",
        "inventario": "lectura",
        "mantenimiento": "lectura",
        "passwords": "lectura",
        "reportes": "lectura",
        "documentos": "lectura",
        "administracion": "ninguno",
        "soporte": "lectura",
        "licencias": "lectura",
        "prestamos": "lectura",
    },
}


def sembrar_roles(apps, schema_editor):
    Rol = apps.get_model("administracion", "Rol")
    PermisoRol = apps.get_model("administracion", "PermisoRol")
    for clave, nombre, orden in ROLES_INICIALES:
        rol, _ = Rol.objects.get_or_create(
            clave=clave,
            defaults={"nombre": nombre, "es_sistema": True, "orden": orden},
        )
        for modulo, nivel in PERMISOS_INICIALES[clave].items():
            PermisoRol.objects.get_or_create(
                rol=rol,
                modulo=modulo,
                defaults={"nivel": nivel},
            )


def quitar_roles(apps, schema_editor):
    Rol = apps.get_model("administracion", "Rol")
    # Los PermisoRol se van en cascada con su rol. El modelo histórico no lleva
    # el delete() que protege a los roles de sistema, así que esto sí borra.
    Rol.objects.filter(clave__in=[fila[0] for fila in ROLES_INICIALES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("administracion", "0007_rol_permisorol"),
    ]

    operations = [
        migrations.RunPython(sembrar_roles, quitar_roles),
    ]
