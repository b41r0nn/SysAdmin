from django import template

from accounts.permisos import PERMISOS_POR_ROL

register = template.Library()


@register.simple_tag(takes_context=True)
def tiene_permiso(context, modulo, nivel="lectura"):
    """Template tag: True si el usuario autenticado tiene al menos `nivel` en `modulo`."""
    user = context.get("user")
    if not user or not user.is_authenticated:
        return False
    permiso = PERMISOS_POR_ROL.get(user.rol, {}).get(modulo, "ninguno")
    if permiso == "ninguno":
        return False
    if nivel == "escritura":
        return permiso == "escritura"
    return True


@register.filter
def get_item(diccionario, clave):
    """Acceso a diccionario por clave variable en plantillas."""
    try:
        return diccionario[clave]
    except (KeyError, TypeError):
        return ""