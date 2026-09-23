from django import forms

from inventario.models import Activo, TIPOS
from mantenimiento.models import PRIORIDADES

from .models import Ticket


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["asunto", "descripcion", "prioridad", "acciones_realizadas", "tiempo_empleado_minutos"]
        widgets = {
            "asunto": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "prioridad": forms.Select(attrs={"class": "form-select"}),
            "acciones_realizadas": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "tiempo_empleado_minutos": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Los campos de trabajo del técnico solo aplican al editar un ticket
        # existente (en la creación el ticket aún no tiene trabajo realizado).
        if self.instance.pk is None:
            for campo in ("acciones_realizadas", "tiempo_empleado_minutos"):
                self.fields.pop(campo, None)


class TicketPublicoForm(forms.Form):
    """Formulario público (LAN interna, sin login) para reportar una falla."""

    nombre = forms.CharField(
        label="Nombre",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Tu nombre"}),
    )
    area = forms.CharField(
        label="Área o departamento",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Recursos Humanos"}),
    )
    contacto = forms.CharField(
        label="Correo o extensión de contacto",
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Opcional"}),
    )
    tipo_dispositivo = forms.ChoiceField(
        label="Tipo de dispositivo",
        choices=[("", "Selecciona el tipo (opcional)")] + TIPOS,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    numero_serie_etiqueta = forms.CharField(
        label="Número de serie o etiqueta del equipo, si lo conocés",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Opcional"}),
    )
    descripcion = forms.CharField(
        label="Descripción del problema",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
    )
    sitio_web = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "off", "tabindex": "-1"}),
    )

    def clean_sitio_web(self):
        return self.cleaned_data.get("sitio_web", "")

    def es_bot(self):
        return bool(self.cleaned_data.get("sitio_web"))


class EscalarTicketForm(forms.Form):
    activo = forms.ModelChoiceField(
        queryset=Activo.objects.all(),
        empty_label="Selecciona un equipo",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    tecnico_asignado = forms.CharField(
        required=False,
        max_length=150,
        label="Técnico asignado",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    prioridad = forms.ChoiceField(
        choices=PRIORIDADES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean_tecnico_asignado(self):
        return self.cleaned_data["tecnico_asignado"].strip()