from django import forms

from .models import Categoria, Documento, TIPOS_DOCUMENTO


class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = [
            "titulo",
            "descripcion",
            "categoria",
            "tipo_documento",
            "archivo",
            "version",
            "fecha_version",
            "activo",
        ]
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "tipo_documento": forms.Select(attrs={"class": "form-select"}),
            "archivo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "version": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej. 1.0"}),
            "fecha_version": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = Categoria.objects.all()
        self.fields["categoria"].required = False


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre", "descripcion", "orden"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "orden": forms.NumberInput(attrs={"class": "form-control"}),
        }


class FiltroDocumentoForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "class": "form-control",
        "placeholder": "Buscar por título...",
    }))
    tipo_documento = forms.ChoiceField(
        required=False,
        choices=[("", "Todos los tipos")] + TIPOS_DOCUMENTO,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    categoria = forms.ModelChoiceField(
        required=False,
        queryset=Categoria.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
        empty_label="Todas las categorías",
    )
