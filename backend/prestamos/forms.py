from datetime import date

from django import forms
from django.core.exceptions import ValidationError

from .models import Prestamo


class PrestamoForm(forms.ModelForm):
    class Meta:
        model = Prestamo
        fields = [
            "activo",
            "solicitante",
            "fecha_prestamo",
            "fecha_devolucion_prevista",
            "destino",
            "observaciones",
        ]
        widgets = {
            "fecha_prestamo": forms.DateInput(attrs={"type": "date"}),
            "fecha_devolucion_prevista": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_activo(self):
        activo = self.cleaned_data.get("activo")
        prestamo_activo = (
            Prestamo.objects.filter(activo=activo, fecha_devolucion__isnull=True)
            .exclude(pk=self.instance.pk if self.instance else None)
            .exists()
        )
        if prestamo_activo:
            raise ValidationError("Este equipo ya tiene un préstamo vigente.")
        return activo

    def clean_fecha_devolucion_prevista(self):
        prevista = self.cleaned_data.get("fecha_devolucion_prevista")
        inicio = self.cleaned_data.get("fecha_prestamo") or date.today()
        if prevista and prevista < inicio:
            raise ValidationError("La devolución prevista no puede ser anterior al préstamo.")
        return prevista