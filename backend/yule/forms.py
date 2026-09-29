from django import forms

from .models import ConfiguracionYule, EquipoOCS


class VincularActivoForm(forms.Form):
    """Elige con qué activo del inventario se vincula un equipo de OCS.

    El selector lleva buscador porque son cientos de activos y el usuario los
    conoce por serial, no por id: un desplegable en crudo no sirve. Se ofrecen
    ordenados por numero_interno para que el orden sea estable y predecible.
    """

    activo = forms.ModelChoiceField(
        queryset=None,
        required=True,
        empty_label="Selecciona un activo…",
        label="Activo del inventario",
    )

    def __init__(self, *args, equipo=None, **kwargs):
        from inventario.models import Activo

        super().__init__(*args, **kwargs)
        self.equipo = equipo
        self.fields["activo"].queryset = Activo.objects.all().order_by(
            "numero_interno", "serial"
        )

    def clean(self):
        limpio = super().clean()
        equipo = self.equipo
        activo = limpio.get("activo")
        if equipo and activo:
            # Un activo con dos equipos OCS obliga a snapshot_software_ocs() a
            # elegir con `.first()`, y ese software es el que acaba en la hoja de
            # vida. Mejor negarlo que colgarle el dato del equipo equivocado.
            otros = activo.equipo_ocs.exclude(pk=equipo.pk)
            if otros.exists():
                nombres = ", ".join(str(o) for o in otros[:3])
                raise forms.ValidationError(
                    f"El activo {activo.serial} ya está vinculado al equipo {nombres}."
                )
        return limpio


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