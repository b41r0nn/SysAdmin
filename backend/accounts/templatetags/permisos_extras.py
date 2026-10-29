from django import template

from accounts.permisos import nivel_permiso, puede_ver_secretos as _puede_ver_secretos

register = template.Library()


@register.simple_tag(takes_context=True)
def tiene_permiso(context, modulo, nivel="lectura"):
    """Template tag: True si el usuario autenticado tiene al menos `nivel` en `modulo`."""
    user = context.get("user")
    if not user or not user.is_authenticated:
        return False
    permiso = nivel_permiso(user.rol, modulo)
    if permiso == "ninguno":
        return False
    if nivel == "escritura":
        return permiso == "escritura"
    return True


@register.simple_tag(takes_context=True)
def puede_ver_secretos(context):
    """Template tag: True si el usuario puede revelar secretos de la bóveda."""
    return _puede_ver_secretos(context.get("user"))


@register.filter
def get_item(diccionario, clave):
    """Acceso a diccionario por clave variable en plantillas."""
    try:
        return diccionario[clave]
    except (KeyError, TypeError):
        return ""
