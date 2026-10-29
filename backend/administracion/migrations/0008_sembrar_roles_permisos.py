from django.db import migrations

# La matriz del código es el origen de las 40 filas. Es la única lectura de
# PERMISOS_POR_ROL que queda fuera del resolvedor, y es legítima: sin ella la
# tabla nacería vacía y todos los roles caerían al respaldo.
from accounts.permisos import PERMISOS_POR_ROL

# (clave, nombre, orden). Los nombres son los de CustomUser.ROL_CHOICES. Los
# cuatro son de sistema: borrar uno dejaría cuentas con un rol inexistente.
ROLES_INICIALES = [
    ("superadmin", "Super Administrador", 10),
    ("admin", "Administrador", 20),
    ("tecnico", "Técnico", 30),
    ("lectura", "Solo lectura", 40),
]


def sembrar_roles(apps, schema_editor):
    Rol = apps.get_model("administracion", "Rol")
    PermisoRol = apps.get_model("administracion", "PermisoRol")
    for clave, nombre, orden in ROLES_INICIALES:
        rol, _ = Rol.objects.get_or_create(
            clave=clave,
            defaults={"nombre": nombre, "es_sistema": True, "orden": orden},
        )
        for modulo, nivel in PERMISOS_POR_ROL[clave].items():
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
