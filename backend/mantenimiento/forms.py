from django import forms

from inventario.models import Activo, CatalogoModelo, TIPOS

from .models import (
    ChecklistItem,
    FotoMantenimiento,
    OrdenMantenimiento,
    PlanMantenimiento,
    Repuesto,
)


def _opciones_categorias(actual=""):
    """Categorías disponibles para un plan: TIPOS + tipos usados en catálogo/activos."""
    opciones = [(t, e) for t, e in TIPOS]
    usados = set(
        list(CatalogoModelo.objects.exclude(tipo_dispositivo="").values_list("tipo_dispositivo", flat=True))
        + list(Activo.objects.exclude(tipo_dispositivo="").values_list("tipo_dispositivo", flat=True))
    )
    for t in sorted(usados):
        if t not in [c[0] for c in opciones]:
            opciones.append((t, t))
    if actual and actual not in [c[0] for c in opciones]:
        opciones.append((actual, actual))
    return opciones


class PlanMantenimientoForm(forms.ModelForm):
    class Meta:
        model = PlanMantenimiento
        fields = [
            "tipo_dispositivo",
            "tipo",
            "criticidad",
            "frecuencia_dias",
            "fecha_inicio",
            "proxima_ejecucion",
            "estado",
            "responsable",
            "observaciones",
        ]
        widgets = {
            "tipo_dispositivo": forms.Select(attrs={"class": "form-select"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "criticidad": forms.Select(attrs={"class": "form-select"}),
            "frecuencia_dias": forms.NumberInput(attrs={"class": "form-control"}),
            "fecha_inicio": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "proxima_ejecucion": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "responsable": forms.TextInput(attrs={"class": "form-control"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        actual = self.instance.tipo_dispositivo if self.instance and self.instance.pk else ""
        self.fields["tipo_dispositivo"].choices = _opciones_categorias(actual)


class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ["descripcion"]
        widgets = {
            "descripcion": forms.TextInput(attrs={"class": "form-control"}),
        }


class ReporteFallaForm(forms.ModelForm):
    class Meta:
        model = OrdenMantenimiento
        fields = ["activo", "prioridad", "descripcion", "foto"]
        widgets = {
            "activo": forms.Select(attrs={"class": "form-select"}),
            "prioridad": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activo"].queryset = Activo.objects.exclude(estado="dado_de_baja")

    def clean(self):
        cleaned_data = super().clean()
        activo = cleaned_data.get("activo")
        if activo and activo.estado == "dado_de_baja":
            self.add_error("activo", "El activo seleccionado está dado de baja.")
        return cleaned_data


class OrdenMantenimientoForm(forms.ModelForm):
    software_snapshot_text = forms.CharField(
        required=False,
        label="Software instalado",
        help_text="Una aplicación por línea (ej: Microsoft Office 365 v16.0)",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Google Chrome\nAdobe Acrobat\n..."}),
    )

    class Meta:
        model = OrdenMantenimiento
        fields = [
            "plan",
            "activo",
            "tipo",
            "estado",
            "prioridad",
            "fecha_apertura",
            "fecha_cierre",
            "tecnico_asignado",
            "descripcion",
            "diagnostico",
            "acciones",
            "costo_estimado",
            "costo_real",
        ]
        widgets = {
            "plan": forms.Select(attrs={"class": "form-select"}),
            "activo": forms.Select(attrs={"class": "form-select"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "prioridad": forms.Select(attrs={"class": "form-select"}),
            "fecha_apertura": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "fecha_cierre": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "tecnico_asignado": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "diagnostico": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "acciones": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "costo_estimado": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "costo_real": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.software_snapshot:
            self.fields["software_snapshot_text"].initial = "\n".join(self.instance.software_snapshot)
        self.fields["plan"].required = False
        self.fields["plan"].queryset = PlanMantenimiento.objects.all()

    def clean_software_snapshot_text(self):
        text = self.cleaned_data.get("software_snapshot_text", "")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines

    def clean(self):
        cleaned_data = super().clean()
        plan = cleaned_data.get("plan")
        activo = cleaned_data.get("activo")
        if plan and activo and plan.tipo_dispositivo != activo.tipo_dispositivo:
            raise forms.ValidationError(
                "El activo no coincide con la categoría del plan seleccionado."
            )
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.software_snapshot = self.cleaned_data.get("software_snapshot_text", [])
        if commit:
            instance.save()
        return instance


class FotoMantenimientoForm(forms.ModelForm):
    class Meta:
        model = FotoMantenimiento
        fields = ["foto", "descripcion"]
        widgets = {
            "foto": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "descripcion": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Antes de limpieza"}),
        }


class RepuestoForm(forms.ModelForm):
    class Meta:
        model = Repuesto
        fields = ["orden", "nombre", "referencia", "cantidad", "costo_unitario"]
        widgets = {
            "orden": forms.Select(attrs={"class": "form-select"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "referencia": forms.TextInput(attrs={"class": "form-control"}),
            "cantidad": forms.NumberInput(attrs={"class": "form-control"}),
            "costo_unitario": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }
