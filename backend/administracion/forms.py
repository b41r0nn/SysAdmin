from django import forms
from django.contrib.auth import get_user_model

from .models import ConfiguracionSistema

CustomUser = get_user_model()


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


class CuentaForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ["username", "email", "rol"]
        widgets = {
            "username": forms.TextInput(attrs={
                "class": "form-control",
                "autocomplete": "off",
            }),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "rol": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if CustomUser.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Ya existe una cuenta con ese nombre de usuario.")
        return username


class CuentaRolForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ["rol"]
        widgets = {"rol": forms.Select(attrs={"class": "form-select"})}