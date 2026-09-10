from django import forms

from .models import LicenciaSoftware, TIPOS_LICENCIA


class LicenciaForm(forms.ModelForm):
    class Meta:
        model = LicenciaSoftware
        fields = [
            "nombre",
            "version",
            "proveedor",
            "clave",
            "tipo",
            "cantidad",
            "fecha_compra",
            "fecha_vencimiento",
            "costo",
            "estado",
            "responsable",
            "activos",
            "observaciones",
        ]
        widgets = {
            "fecha_compra": forms.DateInput(attrs={"type": "date"}),
            "fecha_vencimiento": forms.DateInput(attrs={"type": "date"}),
            "costo": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "activos": forms.SelectMultiple(attrs={"size": "8"}),
        }

    def clean_estado(self):
        # Si existe fecha de vencimiento pasada o próxima, el estado efectivo
        # se calcula igualmente; solo se permite marcar manualmente activa/
        # cancelada para no entrar en conflicto con el cálculo.
        return self.cleaned_data["estado"]