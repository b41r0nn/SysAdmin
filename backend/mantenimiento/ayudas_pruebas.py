"""Ayudantes compartidos por las pruebas de mantenimiento.

El nombre no empieza por ``test``, así que el descubrimiento de pruebas no lo
toma como módulo de pruebas. Los datos son inventados: el repo es público.
"""

from itertools import count

from django.contrib.auth import get_user_model
from django.utils import timezone

from inventario.models import Activo, Asignacion
from usuarios.models import Usuario

# Contenido inicial de los checklists (§B2 del diseño) como
# (sección, descripción, ¿aplica en garantía?). La migración de datos guarda su
# propia copia; las pruebas comparan lo que hay en la base contra estas listas.
PORTATIL = [
    ("Hardware", "Desarme del equipo", False),
    ("Hardware", "Pantalla", False),
    ("Hardware", "Bisagras", False),
    ("Hardware", "Batería", False),
    ("Limpieza", "Limpieza externa", True),
    ("Limpieza", "Limpieza interna", False),
    ("Limpieza", "Limpieza de puertos", False),
    ("Mantenimiento lógico", "Actualizaciones de Windows", True),
    ("Mantenimiento lógico", "Antivirus", True),
    ("Mantenimiento lógico", "Archivos temporales", True),
    ("Mantenimiento lógico", "Estado del disco", True),
    ("Mantenimiento lógico", "Programas de inicio", True),
]
ESCRITORIO = [p for p in PORTATIL if p[1] not in ("Pantalla", "Bisagras", "Batería")]

_numero_de_usuario = count(1)


def crear_usuario(rol="tecnico", **kw):
    """Cuenta de acceso con contraseña "x" y nombre de usuario único.

    ``kw`` pasa tal cual a ``create_user`` (``first_name``, ``is_staff``…).
    """
    kw.setdefault("username", f"ayuda_{rol}_{next(_numero_de_usuario)}")
    kw.setdefault("password", "x")
    return get_user_model().objects.create_user(rol=rol, **kw)


def crear_pc(serial="SN-PC-1", tipo="portatil", compra=None, meses=None, **kw):
    """Activo de prueba.

    ``compra`` es la fecha de compra y ``meses`` los meses de garantía de
    fábrica. Marca "HP", modelo "ProBook" y estado "disponible" son los valores
    por defecto; ``kw`` los sobrescribe y puede traer cualquier otro campo del
    activo (``estado="dado_de_baja"``, ``nombre_equipo``, ``ip_equipo``…).
    """
    datos = {
        "marca": "HP",
        "modelo": "ProBook",
        "estado": "disponible",
        "fecha_compra": compra,
        "garantia_fabrica_meses": meses,
        **kw,
    }
    return Activo.objects.create(serial=serial, tipo_dispositivo=tipo, **datos)


def asignar(activo, nombre="Marta López Gómez", documento="200300400", cargo="Contadora", area="Finanzas"):
    """Deja al activo con responsable: crea el usuario y una asignación activa de hoy."""
    usuario = Usuario.objects.create(
        nombre_completo=nombre,
        documento_identidad=documento,
        cargo=cargo,
        area=area,
        correo="marta@example.com",
    )
    return Asignacion.objects.create(
        activo=activo,
        usuario=usuario,
        fecha_asignacion=timezone.localdate(),
        activa=True,
    )
