from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from inventario.models import Activo, CatalogoModelo, TIPOS

from .models import (
    ESTADOS_FINALES,
    LIMITE_TEXTO_ACTA,
    FotoMantenimiento,
    OrdenMantenimiento,
    PlantillaChecklist,
    PuntoPlantilla,
    Repuesto,
    normalizar_saltos,
)


class TextoActa(forms.CharField):
    """Texto de hasta 600 caracteres; el salto de línea CRLF del navegador cuenta como uno."""

    def to_python(self, value):
        return super().to_python(normalizar_saltos(value) if isinstance(value, str) else value)


def _opciones_categorias(actual=""):
    """Tipos de equipo para un checklist: TIPOS + tipos usados en catálogo/activos."""
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


class OrdenForm(forms.ModelForm):
    """Correctivo (alta y edición). No tiene estado de partes ni casillas de acciones.

    Tampoco expone ``estado`` ni ``fecha_cierre``: un mantenimiento solo se
    cierra por el flujo de cierre, que valida y congela el acta. Un preventivo
    solo deja editar prioridad, fecha, costos y software: el equipo y los textos
    del checklist no se tocan desde aquí.
    """

    diagnostico = TextoActa(
        required=False,
        max_length=LIMITE_TEXTO_ACTA,
        label="Diagnóstico",
        error_messages={"max_length": f"El diagnóstico no puede pasar de {LIMITE_TEXTO_ACTA} caracteres."},
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "maxlength": LIMITE_TEXTO_ACTA}),
    )
    acciones = TextoActa(
        required=False,
        max_length=LIMITE_TEXTO_ACTA,
        label="Solución / acciones realizadas",
        error_messages={"max_length": f"La solución no puede pasar de {LIMITE_TEXTO_ACTA} caracteres."},
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "maxlength": LIMITE_TEXTO_ACTA}),
    )
    software_snapshot_text = forms.CharField(
        required=False,
        label="Software instalado",
        help_text="Una aplicación por línea (ej: Microsoft Office 365 v16.0)",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Google Chrome\nAdobe Acrobat\n..."}),
    )

    class Meta:
        model = OrdenMantenimiento
        fields = [
            "activo",
            "prioridad",
            "fecha_apertura",
            "descripcion",
            "diagnostico",
            "acciones",
            "costo_estimado",
            "costo_real",
        ]
        widgets = {
            "activo": forms.Select(attrs={"class": "form-select"}),
            "prioridad": forms.Select(attrs={"class": "form-select"}),
            "fecha_apertura": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "costo_estimado": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "costo_real": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activo"].queryset = Activo.objects.exclude(estado="dado_de_baja")
        if self.instance and self.instance.pk and self.instance.software_snapshot:
            self.fields["software_snapshot_text"].initial = "\n".join(
                s if isinstance(s, str) else s.get("name", "") for s in self.instance.software_snapshot
            )
        if self.instance.tipo == "preventivo":
            for nombre in ("activo", "descripcion", "diagnostico", "acciones"):
                del self.fields[nombre]

    def clean_software_snapshot_text(self):
        texto = self.cleaned_data.get("software_snapshot_text", "")
        return [linea.strip() for linea in texto.splitlines() if linea.strip()]

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Si el campo no llegó, se conserva el snapshot que ya tenía la orden.
        texto = self.cleaned_data.get("software_snapshot_text")
        if texto or "software_snapshot_text" in self.data or not instance.pk:
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


class NuevoMantenimientoForm(forms.Form):
    """Primer paso de un mantenimiento: qué equipo y de qué tipo."""

    activo = forms.ModelChoiceField(
        queryset=Activo.objects.none(),
        label="Equipo",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    tipo = forms.ChoiceField(
        choices=[("preventivo", "Preventivo"), ("correctivo", "Correctivo")],
        initial="preventivo",
        label="Tipo",
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["activo"].queryset = Activo.objects.exclude(estado="dado_de_baja").order_by("serial")


class CerrarOrdenForm(forms.Form):
    """Cierre de un mantenimiento.

    Las reglas de negocio (checklist completo, fecha no futura…) las valida
    ``ejecucion.errores_para_cerrar``; aquí solo se leen los datos. Si la cuenta
    que cierra no tiene nombre (``pedir_datos_tecnico``), se piden nombres,
    apellidos y cargo, que la vista guarda en la cuenta.
    """

    fecha_cierre = forms.DateField(
        label="Fecha de cierre",
        error_messages={"required": "Indica la fecha de cierre.", "invalid": "Fecha no válida."},
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
    )
    estado_final = forms.ChoiceField(
        label="Estado final del equipo",
        choices=ESTADOS_FINALES,
        error_messages={"required": "Elige el estado final del equipo."},
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    observaciones = TextoActa(
        label="Observaciones",
        required=False,
        max_length=LIMITE_TEXTO_ACTA,
        error_messages={"max_length": f"Las observaciones no pueden pasar de {LIMITE_TEXTO_ACTA} caracteres."},
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    def __init__(self, *args, orden, pedir_datos_tecnico: bool, **kwargs):
        super().__init__(*args, **kwargs)
        self.orden = orden
        self.pedir_datos_tecnico = pedir_datos_tecnico
        self.fields["fecha_cierre"].initial = timezone.localdate()
        # Al cerrar de nuevo una orden reabierta, se parte de lo que tenía.
        if orden.estado_final:
            self.fields["estado_final"].initial = orden.estado_final
        self.fields["observaciones"].initial = orden.observaciones
        if orden.tipo == "correctivo":
            self.fields["diagnostico"] = TextoActa(
                label="Diagnóstico",
                max_length=LIMITE_TEXTO_ACTA,
                initial=orden.diagnostico,
                error_messages={
                    "required": "Escribe el diagnóstico.",
                    "max_length": f"El diagnóstico no puede pasar de {LIMITE_TEXTO_ACTA} caracteres.",
                },
                widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            )
            self.fields["acciones"] = TextoActa(
                label="Solución / acciones realizadas",
                max_length=LIMITE_TEXTO_ACTA,
                initial=orden.acciones,
                error_messages={
                    "required": "Escribe la solución o las acciones realizadas.",
                    "max_length": f"La solución no puede pasar de {LIMITE_TEXTO_ACTA} caracteres.",
                },
                widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            )
        if pedir_datos_tecnico:
            for nombre, etiqueta in (("first_name", "Nombres"), ("last_name", "Apellidos"), ("cargo", "Cargo")):
                self.fields[nombre] = forms.CharField(
                    label=etiqueta,
                    max_length=150,
                    widget=forms.TextInput(attrs={"class": "form-control"}),
                )

    def datos_cierre(self):
        """Argumentos de ``ejecucion.cerrar_orden`` sacados de ``cleaned_data``."""
        nombres = ["fecha_cierre", "estado_final", "observaciones"]
        if self.orden.tipo == "correctivo":
            nombres += ["diagnostico", "acciones"]
        return {n: self.cleaned_data[n] for n in nombres}


EXTENSIONES_ACTA = {".pdf", ".jpg", ".jpeg", ".png"}
LIMITE_ACTA_BYTES = 10 * 1024 * 1024
# Primeros bytes de cada formato (PDF, JPEG, PNG): la extensión se renombra, esto no.
FIRMAS_ACTA = (b"%PDF", bytes.fromhex("ffd8ff"), bytes.fromhex("89504e470d0a1a0a"))


class SubirActaFirmadaForm(forms.Form):
    """El acta firmada escaneada: PDF, JPG o PNG de hasta 10 MB."""

    archivo = forms.FileField(
        label="Acta firmada escaneada",
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png"}),
    )

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        nombre = archivo.name.lower()
        if "." not in nombre or "." + nombre.rsplit(".", 1)[1] not in EXTENSIONES_ACTA:
            raise forms.ValidationError("Sube un PDF, JPG o PNG.")
        if archivo.size > LIMITE_ACTA_BYTES:
            raise forms.ValidationError("El archivo pasa de 10 MB.")
        cabecera = archivo.read(8)
        archivo.seek(0)
        if not cabecera.startswith(FIRMAS_ACTA):
            raise forms.ValidationError("El archivo no es un PDF, JPG o PNG de verdad.")
        return archivo


class ProgramarForm(forms.Form):
    """Fecha en que se acordó hacerle el preventivo a un equipo (vacía: sin fecha)."""

    fecha_programada = forms.DateField(
        required=False,
        error_messages={"invalid": "Fecha no válida."},
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}, format="%Y-%m-%d"),
    )


class PlantillaChecklistForm(forms.ModelForm):
    class Meta:
        model = PlantillaChecklist
        fields = ["tipo_dispositivo", "frecuencia_meses"]
        widgets = {
            "frecuencia_meses": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        campo = self.fields["tipo_dispositivo"]
        existente = bool(self.instance and self.instance.pk)
        actual = self.instance.tipo_dispositivo if existente else ""
        campo.widget = forms.Select(attrs={"class": "form-select"})
        campo.choices = [("", "---------")] + _opciones_categorias(actual)
        if existente:
            # El tipo identifica al checklist: no se cambia después de creado.
            campo.disabled = True

    def clean_tipo_dispositivo(self):
        tipo = self.cleaned_data["tipo_dispositivo"]
        repetidos = PlantillaChecklist.objects.filter(tipo_dispositivo=tipo).exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise forms.ValidationError("Ya existe un checklist para ese tipo de equipo.")
        return tipo


PuntoPlantillaFormSet = inlineformset_factory(
    PlantillaChecklist,
    PuntoPlantilla,
    fields=["seccion", "descripcion", "posicion", "aplica_en_garantia", "activo"],
    widgets={
        "seccion": forms.TextInput(attrs={"class": "form-control", "list": "secciones-sugeridas"}),
        "descripcion": forms.TextInput(attrs={"class": "form-control"}),
        "posicion": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        "aplica_en_garantia": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
    },
    extra=3,
    can_delete=True,
)
