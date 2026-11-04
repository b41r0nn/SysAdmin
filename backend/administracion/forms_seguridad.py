"""Formulario de la política de seguridad.

Va en su propio módulo y no en ``forms.py`` para que la pantalla de Empresa
siga declarando su lista explícita de campos: los cuatro campos nuevos del
modelo no se cuelan en ningún otro formulario.
"""

from django import forms

from .models import (
    HORAS_DE_BLOQUEO_MAXIMO,
    HORAS_DE_BLOQUEO_MINIMO,
    INTENTOS_MAXIMO,
    INTENTOS_MINIMO,
    LONGITUD_MINIMA_MAXIMA,
    LONGITUD_MINIMA_MINIMA,
    SESION_MINUTOS_MAXIMO,
    SESION_MINUTOS_MINIMO,
    ConfiguracionSistema,
)


def _numero(minimo, maximo):
    return forms.NumberInput(attrs={"class": "form-control", "min": minimo, "max": maximo})


class SeguridadForm(forms.ModelForm):
    """Los cuatro valores de la política de seguridad.

    Los mínimos y los máximos son validadores del modelo y los corre
    ``_post_clean()``: así la regla vale también para un comando de gestión o
    una importación, no solo para esta pantalla. El ``min``/``max`` del HTML es
    comodidad del navegador, no la validación.

    Y ni el formulario ni el modelo son la última línea: un ``queryset.update()``
    se salta los dos. Quien de verdad garantiza que ningún valor guardado tumbe
    el login es ``administracion.seguridad``, que acota al leer.
    """

    class Meta:
        model = ConfiguracionSistema
        fields = [
            "sesion_minutos",
            "intentos_antes_de_bloquear",
            "horas_de_bloqueo",
            "longitud_minima_password",
        ]
        widgets = {
            "sesion_minutos": _numero(SESION_MINUTOS_MINIMO, SESION_MINUTOS_MAXIMO),
            "intentos_antes_de_bloquear": _numero(INTENTOS_MINIMO, INTENTOS_MAXIMO),
            "horas_de_bloqueo": _numero(HORAS_DE_BLOQUEO_MINIMO, HORAS_DE_BLOQUEO_MAXIMO),
            "longitud_minima_password": _numero(LONGITUD_MINIMA_MINIMA, LONGITUD_MINIMA_MAXIMA),
        }
