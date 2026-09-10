from django import forms

from .models import ConfiguracionSistema


class ConfiguracionForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionSistema
        fields = [
            "nombre_empresa",
            "nit",
            "direccion",
            "telefono",
            "email_contacto",
            "pie_firma_reporte",
        ]
        widgets = {
            "nombre_empresa": forms.TextInput(attrs={"class": "form-control"}),
            "nit": forms.TextInput(attrs={"class": "form-control"}),
            "direccion": forms.TextInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "email_contacto": forms.EmailInput(attrs={"class": "form-control"}),
            "pie_firma_reporte": forms.TextInput(attrs={"class": "form-control"}),
        }