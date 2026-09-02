from django import forms

from .models import Credencial, Vault


class VaultForm(forms.ModelForm):
    acceso_codigo = forms.CharField(
        label="Codigo de acceso",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        help_text="Si se define, se usara para desbloquear credenciales.",
    )

    class Meta:
        model = Vault
        fields = ["nombre", "descripcion", "acceso_requerido"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "acceso_requerido": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned = super().clean()
        acceso_requerido = cleaned.get("acceso_requerido")
        acceso_codigo = cleaned.get("acceso_codigo")
        if acceso_requerido and not acceso_codigo and not self.instance.acceso_hash:
            self.add_error("acceso_codigo", "Debes definir un codigo de acceso.")
        return cleaned

    def save(self, commit=True):
        vault = super().save(commit=False)
        acceso_codigo = self.cleaned_data.get("acceso_codigo")
        acceso_requerido = self.cleaned_data.get("acceso_requerido")
        if acceso_requerido:
            if acceso_codigo:
                vault.set_access_code(acceso_codigo)
        else:
            vault.set_access_code("")
        if commit:
            vault.save()
        return vault


class CredencialForm(forms.ModelForm):
    secreto = forms.CharField(
        label="Secreto",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}, render_value=True),
        help_text="Deja vacio para mantener el secreto actual.",
    )

    class Meta:
        model = Credencial
        fields = [
            "titulo",
            "usuario",
            "url",
            "notas",
            "estado",
            "fecha_expiracion",
        ]
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "form-control"}),
            "usuario": forms.TextInput(attrs={"class": "form-control"}),
            "url": forms.URLInput(attrs={"class": "form-control"}),
            "notas": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "fecha_expiracion": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def save(self, commit=True):
        credencial = super().save(commit=False)
        secreto = self.cleaned_data.get("secreto")
        if secreto:
            credencial.set_secret(secreto)
        if commit:
            credencial.save()
        return credencial
