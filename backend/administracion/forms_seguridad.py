"""Formulario de la política de seguridad.

Va en su propio módulo y no en ``forms.py`` para que la pantalla de Empresa
siga declarando su lista explícita de campos: los cuatro campos nuevos del
modelo no se cuelan en ningún otro formulario.
"""

from django import forms

from .models import ConfiguracionSistema


class SeguridadForm(forms.ModelForm):
    """Los cuatro valores de la política de seguridad.

    Los mínimos (sesión ≥ 1 minuto, intentos ≥ 1, contraseña ≥ 8 caracteres)
    son validadores del modelo y los corre ``_post_clean()``: así la regla vale
    también para un comando de gestión o una importación, no solo para esta
    pantalla. El ``min`` del HTML es comodidad del navegador, no la validación.
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
            "sesion_minutos": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "intentos_antes_de_bloquear": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "horas_de_bloqueo": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "longitud_minima_password": forms.NumberInput(attrs={"class": "form-control", "min": 8}),
        }
