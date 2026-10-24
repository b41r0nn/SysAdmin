import json

from django import forms
from django.forms import inlineformset_factory
from django.urls import reverse
from django.utils import timezone

from inventario.models import Activo, CatalogoModelo, TIPOS

from .constants import PARTES_POR_TIPO
from .models import (
    ESTADOS_FINALES,
    LIMITE_TEXTO_ACTA,
    ChecklistItem,
    FotoMantenimiento,
    OrdenMantenimiento,
    PlanMantenimiento,
    PlantillaChecklist,
    PuntoPlantilla,
    Repuesto,
)


ESTADO_PARTE_CHOICES = [
    ("bien", "Buen estado"),
    ("mal", "Mal estado"),
]


def _partes_por_activo(activo):
    if not activo:
        return []
    tipo = getattr(activo, "tipo_dispositivo", "")
    return PARTES_POR_TIPO.get(tipo, [])


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
            "fecha_inicio": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "proxima_ejecucion": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "responsable": forms.TextInput(attrs={"class": "form-control"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        actual = self.instance.tipo_dispositivo if self.instance and self.instance.pk else ""
        opciones = _opciones_categorias(actual)
        self.fields["tipo_dispositivo"].choices = opciones
        if isinstance(self.fields["tipo_dispositivo"].widget, forms.Select):
            self.fields["tipo_dispositivo"].widget.choices = opciones


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
            "accion_limpieza_general",
            "accion_mantenimiento_logico",
            "accion_cambio_pasta_termica",
            "accion_cambio_parte",
            "accion_cambio_parte_detalle",
            "costo_estimado",
            "costo_real",
        ]
        labels = {
            "acciones": "Notas adicionales",
            "accion_limpieza_general": "Limpieza general",
            "accion_mantenimiento_logico": "Mantenimiento lógico",
            "accion_cambio_pasta_termica": "Cambio de pasta térmica",
            "accion_cambio_parte": "Cambio de parte",
            "accion_cambio_parte_detalle": "Detalle del cambio de parte",
        }
        widgets = {
            "plan": forms.Select(attrs={"class": "form-select"}),
            "activo": forms.Select(attrs={"class": "form-select"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "prioridad": forms.Select(attrs={"class": "form-select"}),
            "fecha_apertura": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "fecha_cierre": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "tecnico_asignado": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "diagnostico": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "acciones": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "accion_limpieza_general": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "accion_mantenimiento_logico": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "accion_cambio_pasta_termica": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "accion_cambio_parte": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "accion_cambio_parte_detalle": forms.TextInput(attrs={"class": "form-control"}),
            "costo_estimado": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "costo_real": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.software_snapshot:
            self.fields["software_snapshot_text"].initial = "\n".join(self.instance.software_snapshot)
        self.fields["plan"].required = False
        self.fields["plan"].queryset = PlanMantenimiento.objects.all()
        self.fields["activo"].widget.attrs.update({
            "hx-get": reverse("mantenimiento:estado_partes_partial"),
            "hx-trigger": "change",
            "hx-target": "#estado-partes-container",
            "hx-vals": json.dumps({
                "orden": self.instance.pk if self.instance and self.instance.pk else ""
            }),
        })
        self._agregar_campos_estado_partes()

    def _activo_para_partes(self):
        activo_pk = self.data.get("activo")
        if activo_pk:
            try:
                return Activo.objects.get(pk=activo_pk)
            except Activo.DoesNotExist:
                return None
        if self.instance and self.instance.pk and self.instance.activo_id:
            return self.instance.activo
        activo = self.initial.get("activo")
        if isinstance(activo, Activo):
            return activo
        if activo:
            try:
                return Activo.objects.get(pk=activo)
            except Activo.DoesNotExist:
                return None
        return None

    def _agregar_campos_estado_partes(self):
        activo = self._activo_para_partes()
        guardados = {}
        if self.instance and self.instance.pk and self.instance.estado_partes:
            guardados = self.instance.estado_partes
        for slug, label in _partes_por_activo(activo):
            nombre_campo = f"parte_{slug}"
            self.fields[nombre_campo] = forms.ChoiceField(
                label=label,
                choices=ESTADO_PARTE_CHOICES,
                required=False,
                widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
                initial=guardados.get(slug, ""),
            )

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
        if cleaned_data.get("accion_cambio_parte") and not cleaned_data.get("accion_cambio_parte_detalle", "").strip():
            self.add_error("accion_cambio_parte_detalle", "Indicá qué parte se cambió.")
        return cleaned_data

    def _estado_partes_desde_cleaned(self):
        estado = {}
        for nombre, valor in self.cleaned_data.items():
            if nombre.startswith("parte_") and valor:
                estado[nombre[6:]] = valor
        return estado

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.software_snapshot = self.cleaned_data.get("software_snapshot_text", [])
        instance.estado_partes = self._estado_partes_desde_cleaned()
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
    observaciones = forms.CharField(
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
            self.fields["diagnostico"] = forms.CharField(
                label="Diagnóstico",
                max_length=LIMITE_TEXTO_ACTA,
                initial=orden.diagnostico,
                error_messages={
                    "required": "Escribe el diagnóstico.",
                    "max_length": f"El diagnóstico no puede pasar de {LIMITE_TEXTO_ACTA} caracteres.",
                },
                widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            )
            self.fields["acciones"] = forms.CharField(
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
