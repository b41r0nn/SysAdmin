from django import forms

from inventario.models import Activo

from .models import ChecklistItem, OrdenMantenimiento, PlanMantenimiento, Repuesto


class PlanMantenimientoForm(forms.ModelForm):
    class Meta:
        model = PlanMantenimiento
        fields = [
            "activo",
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
            "activo": forms.Select(attrs={"class": "form-select"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "criticidad": forms.Select(attrs={"class": "form-select"}),
            "frecuencia_dias": forms.NumberInput(attrs={"class": "form-control"}),
            "fecha_inicio": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "proxima_ejecucion": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "responsable": forms.TextInput(attrs={"class": "form-control"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


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

    def clean(self):
        cleaned_data = super().clean()
        plan = cleaned_data.get("plan")
        activo = cleaned_data.get("activo")
        if plan and activo and plan.activo_id != activo.id:
            raise forms.ValidationError("El activo debe coincidir con el plan seleccionado.")
        return cleaned_data


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
