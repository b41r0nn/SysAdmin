from django import forms

from .models import ConfiguracionYule


class ConfiguracionYuleForm(forms.ModelForm):
    """Formulario para editar la conexión OCS desde la pantalla de Yule."""

    ocs_password = forms.CharField(
        label="Contraseña",
        required=False,
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "autocomplete": "new-password",
        }),
        help_text="Dejar en blanco para conservar la contraseña actual.",
    )

    class Meta:
        model = ConfiguracionYule
        fields = [
            "url",
            "usuario",
            "integracion_activa",
            "auto_sync_habilitado",
            "frecuencia_sync_minutos",
            "descripcion",
        ]
        widgets = {
            "url": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "https://srv.ocs.redihos.local:8443/ocsapi/v1",
            }),
            "usuario": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "usuario_ocs",
            }),
            "integracion_activa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "auto_sync_habilitado": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "frecuencia_sync_minutos": forms.NumberInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def clean_url(self):
        url = (self.cleaned_data.get("url") or "").strip()
        return url.rstrip("/")

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw = self.cleaned_data.get("ocs_password")
        if raw:
            instance.set_ocs_password(raw)
        if commit:
            instance.save()
        return instance