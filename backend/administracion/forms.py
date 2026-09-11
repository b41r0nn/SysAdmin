from django import forms
from django.contrib.auth import get_user_model

from .models import ConfiguracionSistema

CustomUser = get_user_model()


class ConfiguracionForm(forms.ModelForm):
    smtp_password = forms.CharField(
        label="Contraseña SMTP",
        required=False,
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "autocomplete": "new-password",
        }),
        help_text="Deja en blanco para conservar la contraseña actual.",
    )

    class Meta:
        model = ConfiguracionSistema
        fields = [
            "nombre_empresa",
            "nit",
            "direccion",
            "telefono",
            "email_contacto",
            "pie_firma_reporte",
            "smtp_host",
            "smtp_puerto",
            "smtp_usuario",
            "smtp_usa_tls",
            "smtp_usa_ssl",
        ]
        widgets = {
            "nombre_empresa": forms.TextInput(attrs={"class": "form-control"}),
            "nit": forms.TextInput(attrs={"class": "form-control"}),
            "direccion": forms.TextInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "email_contacto": forms.EmailInput(attrs={"class": "form-control"}),
            "pie_firma_reporte": forms.TextInput(attrs={"class": "form-control"}),
            "smtp_host": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "smtp.office365.com",
            }),
            "smtp_puerto": forms.NumberInput(attrs={"class": "form-control"}),
            "smtp_usuario": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "soporte@redihos.co",
            }),
            "smtp_usa_tls": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "smtp_usa_ssl": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["smtp_puerto"].required = False

    def clean_smtp_puerto(self):
        value = self.cleaned_data.get("smtp_puerto")
        if not value:
            return 587
        return value

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw = self.cleaned_data.get("smtp_password")
        if raw:
            instance.set_smtp_password(raw)
        if commit:
            instance.save()
        return instance


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