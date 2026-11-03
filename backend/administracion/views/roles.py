"""Matriz de roles × módulos: qué puede ver y hacer cada rol en cada módulo."""

from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from accounts.permisos import requiere_permiso
from core.utils import get_client_ip

from ..models import Modulo, PermisoRol, Rol
from ..registro import nivel_de
from ..services import registrar_auditoria

# El superadministrador es la llave de repuesto del sistema: si su columna se
# pudiera degradar, un descuido dejaría la configuración sin nadie que entre a
# arreglarla. El resolvedor ya le da escritura siempre; aquí se le cierra
# además la puerta de escritura, para que la tabla no quede diciendo una cosa
# distinta de lo que el sistema aplica.
ROL_INTOCABLE = "superadmin"

# {clave: etiqueta} de los tres únicos niveles válidos.
NIVELES = dict(PermisoRol.NIVEL_CHOICES)


def _celda(rol, modulo, nivel):
    """Lo que la plantilla necesita para pintar una celda de la matriz."""
    return {
        "rol": rol,
        "modulo": modulo,
        "nivel": nivel,
        "etiqueta": NIVELES.get(nivel, nivel),
        "fijo": rol.clave == ROL_INTOCABLE,
    }


@requiere_permiso("administracion", "lectura")
def roles(request):
    """Pinta la matriz: una fila por módulo, una columna por rol.

    Se muestran los diez módulos, también los apagados: hay que poder dejar los
    permisos listos antes de encender uno. Por eso cada celda trae lo que hay
    GUARDADO en la tabla (``nivel_de``) y no lo que el sistema aplica hoy
    (``nivel_permiso``), que para un módulo apagado respondería «ninguno» y
    convertiría la pantalla en una mentira sobre lo que se está editando. El
    apagado se avisa en la propia fila.

    ``nivel_de`` lee el diccionario cacheado, así que las cuarenta celdas salen
    de una sola consulta.
    """
    filas_rol = list(Rol.objects.all())
    filas = [
        {
            "modulo": modulo,
            "celdas": [
                _celda(rol, modulo, nivel_de(rol.clave, modulo.clave)) for rol in filas_rol
            ],
        }
        for modulo in Modulo.objects.all()
    ]
    return render(request, "administracion/roles_matriz.html", {
        "roles": filas_rol,
        "filas": filas,
        "niveles": PermisoRol.NIVEL_CHOICES,
    })


@requiere_permiso("administracion", "escritura")
@require_POST
def guardar_permiso(request, rol, modulo):
    """Guarda una celda de la matriz y devuelve el parcial para que HTMX la reemplace."""
    fila_rol = get_object_or_404(Rol, clave=rol)
    fila_modulo = get_object_or_404(Modulo, clave=modulo)
    if fila_rol.clave == ROL_INTOCABLE:
        # El texto fijo de la plantilla no es una validación: el POST directo
        # llega igual y es exactamente el que hay que rechazar.
        return HttpResponseBadRequest(
            f"El rol «{fila_rol.nombre}» siempre tiene escritura y no se puede cambiar."
        )
    nivel = request.POST.get("nivel", "")
    if nivel not in NIVELES:
        # El <select> de tres opciones tampoco es una validación. No se repite
        # aquí el valor recibido: la respuesta se pinta como HTML.
        return HttpResponseBadRequest(
            "El nivel no es válido: solo se acepta ninguno, lectura o escritura."
        )
    anterior = nivel_de(fila_rol.clave, fila_modulo.clave)
    try:
        # update_or_create guarda por instancia: corren el full_clean() de
        # PermisoRol.save() (segunda barrera) y la señal que limpia la caché.
        # Un queryset.update() se saltaría las dos y la pantalla seguiría
        # mostrando el permiso viejo hasta que la caché venza.
        permiso, _ = PermisoRol.objects.update_or_create(
            rol=fila_rol,
            modulo=fila_modulo.clave,
            defaults={"nivel": nivel},
        )
    except ValidationError as error:
        return HttpResponseBadRequest(" ".join(error.messages))
    registrar_auditoria(
        request.user,
        "administracion",
        "configurar",
        objeto=permiso,
        detalle=(
            f"Permiso de «{fila_rol.nombre}» en «{fila_modulo.nombre}»: "
            f"de {NIVELES.get(anterior, anterior)} a {NIVELES[nivel]}"
        ),
        ip=get_client_ip(request),
    )
    return render(request, "administracion/partials/celda_permiso.html", {
        "celda": _celda(fila_rol, fila_modulo, permiso.nivel),
        "niveles": PermisoRol.NIVEL_CHOICES,
    })
