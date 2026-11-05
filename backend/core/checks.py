from django.conf import settings
from django.core.checks import Warning, register
from django.db import Error as ErrorDeBaseDeDatos


@register()
def check_passwords_encryption_key(app_configs, **kwargs):
    """W001: la clave del vault debe estar definida explícitamente.

    Si falta, passwords.crypto.build_fernet() la deriva de SECRET_KEY: rotar
    SECRET_KEY deja ilegibles los secretos del vault y las claves SMTP/OCS.
    """
    if getattr(settings, "PASSWORDS_ENCRYPTION_KEY", ""):
        return []
    return [
        Warning(
            "PASSWORDS_ENCRYPTION_KEY no está configurado: la clave del vault "
            "se deriva de SECRET_KEY y una rotación de SECRET_KEY deja "
            "ilegibles los secretos guardados.",
            hint="Define PASSWORDS_ENCRYPTION_KEY (una clave Fernet) en .env.",
            id="sysadmin.W001",
        )
    ]


@register()
def check_modulos_sembrados(app_configs, **kwargs):
    """W002: toda clave de ``accounts.permisos.MODULOS`` necesita su fila.

    La pantalla de módulos y la matriz de roles iteran ``Modulo.objects.all()``,
    así que un módulo sin fila no sale en ninguna de las dos y sus permisos
    quedan ineditables. Hoy la migración ``0006_sembrar_modulos`` siembra los
    diez; esto avisa el día que alguien añada una clave a ``MODULOS`` y olvide
    la siembra.

    Los imports son locales porque este módulo se carga desde
    ``CoreConfig.ready()``: en la cabecera cerraría el ciclo con los modelos.

    El chequeo corre también antes de ``migrate``, sobre una base donde la tabla
    todavía no existe, así que un error de base no puede reventar ``manage.py``:
    es el mismo blindaje que ``administracion.registro.roles_choices``. No se
    registra el fallo porque aquí no se concede ningún acceso y ese mismo error
    de base ya deja traza en el catálogo de módulos.

    Se captura ``django.db.Error``, la **base de la jerarquía**, y no
    ``DatabaseError``: el ``InterfaceError`` de psycopg («connection already
    closed») hereda de ``Error`` y no de ``DatabaseError``, así que con el
    ``except`` estrecho tumbaba cualquier ``manage.py`` —el ``migrate`` de un
    despliegue incluido—. Solo muerde en PostgreSQL, que es producción.
    """
    from accounts.permisos import MODULOS
    from administracion.models import Modulo

    try:
        sembrados = set(Modulo.objects.values_list("clave", flat=True))
    except ErrorDeBaseDeDatos:
        return []
    faltantes = [clave for clave in MODULOS if clave not in sembrados]
    if not faltantes:
        return []
    return [
        Warning(
            "Estos módulos de accounts.permisos.MODULOS no tienen fila en el "
            f"catálogo de módulos: {', '.join(faltantes)}. No aparecen en la "
            "pantalla de módulos ni en la matriz de roles, así que sus permisos "
            "no se pueden editar.",
            hint=(
                "Añade una migración de datos que siembre la fila, como "
                "administracion/migrations/0006_sembrar_modulos.py."
            ),
            id="sysadmin.W002",
        )
    ]
