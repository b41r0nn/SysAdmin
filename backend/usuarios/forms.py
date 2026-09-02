import os

from django import forms
from .models import Usuario


ALLOWED_PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


class UsuarioForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = [
            "nombre_completo",
            "documento_identidad",
            "cargo",
            "area",
            "correo",
            "telefono",
            "estado",
            "foto",
        ]
        widgets = {
            "nombre_completo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Nombre completo",
            }),
            "documento_identidad": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Cédula o documento",
            }),
            "cargo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Cargo",
            }),
            "area": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Área o departamento",
            }),
            "correo": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "correo@empresa.com",
            }),
            "telefono": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Teléfono o extensión",
            }),
            "estado": forms.Select(attrs={
                "class": "form-select",
            }),
            "foto": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
            }),
        }

    def clean_foto(self):
        foto = self.cleaned_data.get('foto')
        if foto:
            ext = os.path.splitext(foto.name)[1].lower()
            if ext not in ALLOWED_PHOTO_EXTENSIONS:
                raise forms.ValidationError(
                    "Tipo de imagen no permitido. Solo JPG, PNG, GIF o WEBP."
                )
        return foto
