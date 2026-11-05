from django.core.exceptions import FieldDoesNotExist

from .services import registrar_auditoria

LARGO_MAXIMO_VALOR = 100


def _etiqueta(form, nombre):
    campo = form.fields.get(nombre)
    if campo is not None and campo.label:
        return str(campo.label)
    modelo = getattr(form._meta, "model", None)
    if modelo is not None:
        try:
            return str(modelo._meta.get_field(nombre).verbose_name)
        except FieldDoesNotExist:  # campo que no es del modelo
            pass
    return nombre


def _texto(valor):
    if valor is None or valor == "":
        return "(vacío)"
    if valor is True:
        return "Sí"
    if valor is False:
        return "No"
    texto = str(valor)
    if len(texto) > LARGO_MAXIMO_VALOR:
        texto = texto[:LARGO_MAXIMO_VALOR]
    return texto


def auditar_cambios(usuario, form, modulo="administracion", objeto=None, ip="", secretos=()):
    """Registra un RegistroAuditoria por cada campo que cambió un ModelForm.

    El detalle es «etiqueta»: anterior → nuevo. Los campos en `secretos` se
    registran como «etiqueta»: (cambiada), sin el valor anterior ni el nuevo.
    Solo para guardados por formulario; los cambios sin formulario llaman
    directamente a `registrar_auditoria`. Devuelve el número de campos
    registrados.
    """
    if objeto is None:
        objeto = getattr(form, "instance", None)
    registrados = 0
    for nombre in form.changed_data:
        etiqueta = _etiqueta(form, nombre)
        if nombre in secretos:
            detalle = f"«{etiqueta}»: (cambiada)"
        else:
            anterior = _texto(form.initial.get(nombre))
            nuevo = _texto(form.cleaned_data.get(nombre))
            detalle = f"«{etiqueta}»: {anterior} → {nuevo}"
        registrar_auditoria(
            usuario, modulo, "configurar", objeto=objeto, detalle=detalle, ip=ip,
        )
        registrados += 1
    return registrados
