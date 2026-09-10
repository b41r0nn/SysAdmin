from django import forms

from inventario.models import Activo
from mantenimiento.models import PRIORIDADES

from .models import Ticket


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["asunto", "descripcion", "prioridad"]
        widgets = {
            "asunto": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "prioridad": forms.Select(attrs={"class": "form-select"}),
        }


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