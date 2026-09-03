import os

from django import forms

from .models import Activo, CatalogoModelo

ALLOWED_ACTA_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png'}

# ── Campos por tipo ────────────────────────────────────────────────────────────
CAMPOS_CELULAR = [
    "imei", "almacenamiento", "ram_celular", "procesador_celular",
    "tipo_disco_celular", "cuenta_correo_dispositivo", "numero_linea", "operador",
]
CAMPOS_PC = [
    "nombre_equipo", "disco_capacidad", "tipo_disco", "ram", "procesador",
    "sistema_operativo", "licencia_so", "usuario_red", "usuario_admin_local",
    "ip_equipo", "mac_equipo",
]
CAMPOS_TELEFONO = ["extension", "puerto_jack", "linea_asignada"]
CAMPOS_MONITOR = ["pulgadas", "resolucion", "tipo_panel", "conectores"]

CAMPOS_TIPO = {
    "celular": CAMPOS_CELULAR,
    "escritorio": CAMPOS_PC,
    "portatil": CAMPOS_PC,
    "telefono_fijo": CAMPOS_TELEFONO,
    "monitor": CAMPOS_MONITOR,
}

CAMPOS_COMUNES = [
    "tipo_dispositivo", "catalogo", "marca", "modelo", "serial", "estado",
    "ubicacion_fisica", "fecha_compra", "proveedor", "valor_compra",
    "garantia_fabrica_meses", "garantia_extendida", "anios_garantia_extendida",
    "foto_activo", "observaciones",
]

ALL_SPECIFIC = CAMPOS_CELULAR + CAMPOS_PC + CAMPOS_TELEFONO + CAMPOS_MONITOR


class ActivoForm(forms.ModelForm):
    class Meta:
        model = Activo
        fields = CAMPOS_COMUNES + ALL_SPECIFIC
        widgets = {
            "tipo_dispositivo": forms.Select(attrs={"class": "form-select", "id": "id_tipo_dispositivo"}),
            "catalogo": forms.Select(attrs={"class": "form-select", "id": "id_catalogo"}),
            "marca": forms.TextInput(attrs={"class": "form-control"}),
            "modelo": forms.TextInput(attrs={"class": "form-control"}),
            "serial": forms.TextInput(attrs={"class": "form-control"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "ubicacion_fisica": forms.TextInput(attrs={"class": "form-control"}),
            "fecha_compra": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "proveedor": forms.TextInput(attrs={"class": "form-control"}),
            "valor_compra": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "garantia_fabrica_meses": forms.NumberInput(attrs={"class": "form-control"}),
            "garantia_extendida": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "anios_garantia_extendida": forms.NumberInput(attrs={"class": "form-control"}),
            "foto_activo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            # Celular
            "imei": forms.TextInput(attrs={"class": "form-control"}),
            "almacenamiento": forms.TextInput(attrs={"class": "form-control"}),
            "ram_celular": forms.TextInput(attrs={"class": "form-control"}),
            "procesador_celular": forms.TextInput(attrs={"class": "form-control"}),
            "tipo_disco_celular": forms.TextInput(attrs={"class": "form-control"}),
            "cuenta_correo_dispositivo": forms.EmailInput(attrs={"class": "form-control"}),
            "numero_linea": forms.TextInput(attrs={"class": "form-control"}),
            "operador": forms.TextInput(attrs={"class": "form-control"}),
            # PC
            "nombre_equipo": forms.TextInput(attrs={"class": "form-control", "placeholder": "PC-CONTABILIDAD-01"}),
            "disco_capacidad": forms.TextInput(attrs={"class": "form-control"}),
            "tipo_disco": forms.TextInput(attrs={"class": "form-control"}),
            "ram": forms.TextInput(attrs={"class": "form-control"}),
            "procesador": forms.TextInput(attrs={"class": "form-control"}),
            "sistema_operativo": forms.TextInput(attrs={"class": "form-control"}),
            "licencia_so": forms.TextInput(attrs={"class": "form-control"}),
            "usuario_red": forms.TextInput(attrs={"class": "form-control"}),
            "usuario_admin_local": forms.TextInput(attrs={"class": "form-control"}),
            "ip_equipo": forms.TextInput(attrs={"class": "form-control", "placeholder": "192.168.1.x"}),
            "mac_equipo": forms.TextInput(attrs={"class": "form-control", "placeholder": "AA:BB:CC:DD:EE:FF"}),
            # Teléfono Fijo
            "extension": forms.TextInput(attrs={"class": "form-control"}),
            "puerto_jack": forms.TextInput(attrs={"class": "form-control"}),
            "linea_asignada": forms.TextInput(attrs={"class": "form-control"}),
            # Monitor
            "pulgadas": forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
            "resolucion": forms.TextInput(attrs={"class": "form-control", "placeholder": "1920x1080"}),
            "tipo_panel": forms.TextInput(attrs={"class": "form-control", "placeholder": "IPS / VA / TN"}),
            "conectores": forms.TextInput(attrs={"class": "form-control", "placeholder": "HDMI, DisplayPort, VGA"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Catálogo es opcional: permite crear/editar activos sin elegir modelo de catálogo
        self.fields["catalogo"].required = False
        # Make all specific fields optional at form level (model already nullable)
        for campo in ALL_SPECIFIC:
            self.fields[campo].required = False


class CatalogoModeloForm(forms.ModelForm):
    class Meta:
        model = CatalogoModelo
        fields = ["tipo_dispositivo", "marca", "modelo", "especificaciones_json"]
        widgets = {
            "tipo_dispositivo": forms.Select(attrs={"class": "form-select"}),
            "marca": forms.TextInput(attrs={"class": "form-control"}),
            "modelo": forms.TextInput(attrs={"class": "form-control"}),
            "especificaciones_json": forms.Textarea(
                attrs={"class": "form-control font-mono", "rows": 4, "placeholder": '{"ram": "8GB", "disco": "512GB"}'}
            ),
        }


class AsignacionForm(forms.ModelForm):
    class Meta:
        from .models import Asignacion
        model = Asignacion
        fields = ["usuario", "observaciones"]
        widgets = {
            "usuario": forms.Select(attrs={"class": "form-select"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Observaciones sobre la asignación..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from usuarios.models import Usuario
        self.fields["usuario"].queryset = Usuario.objects.filter(estado="activo")


class DevolucionForm(forms.Form):
    observaciones = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Motivo o estado de la devolución..."}),
        required=False
    )


class TrasladoForm(forms.Form):
    usuario_destino = forms.ModelChoiceField(
        queryset=None,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Usuario Destino"
    )
    observaciones = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Motivo del traslado..."}),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from usuarios.models import Usuario
        self.fields["usuario_destino"].queryset = Usuario.objects.filter(estado="activo")


class SubirActaForm(forms.Form):
    escaneado_firmado = forms.FileField(
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
        label="Acta Firmada (PDF/Imagen)"
    )

    def clean_escaneado_firmado(self):
        file = self.cleaned_data.get('escaneado_firmado')
        if file:
            ext = os.path.splitext(file.name)[1].lower()
            if ext not in ALLOWED_ACTA_EXTENSIONS:
                raise forms.ValidationError(
                    "Tipo de archivo no permitido. Solo PDF, JPG o PNG."
                )
        return file
