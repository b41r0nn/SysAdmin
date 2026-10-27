# Mantenimiento v2 (checklists, programación por equipo y acta de una hoja) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar los planes por categoría por cuatro piezas:
- checklists por tipo de equipo, que se copian a cada mantenimiento y obligan a marcar cada punto antes de cerrar;
- una programación por equipo, flexible y basada en la garantía, con un ciclo de 12 meses;
- un acta PDF de una sola hoja carta, con QR, fotos y firmas;
- la carga del acta firmada.

**Architecture:** La lógica vive en módulos de servicio puros y probados por separado:
- `mantenimiento/programacion.py` responde a qué equipo le toca;
- `mantenimiento/ejecucion.py` se encarga de iniciar, marcar, cerrar, reabrir y congelar los datos;
- `mantenimiento/acta.py` arma y renderiza el acta.

Las vistas se parten en un paquete `mantenimiento/views/`, igual que `inventario/views/`. Al cerrar, el acta congela sus datos en `OrdenMantenimiento.datos_acta` (JSON) y siempre se genera desde ahí. Los planes se retiran al final, cuando todo lo que los usaba ya tiene reemplazo.

**Tech Stack:** Django 5.2, HTMX (django-htmx), Bootstrap 5, WeasyPrint 70 (PDF), qrcode y openpyxl.

**Spec:** `docs/superpowers/specs/2026-10-23-mantenimiento-y-contrasenas-design.md` (Parte B). Bocetos aprobados en `docs/superpowers/specs/2026-10-23-bocetos/` (`programacion.html` y `acta-una-hoja.html`).

## Global Constraints

- Comando de pruebas (Git Bash, desde `backend/`): `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test <etiqueta> --noinput`. En Windows, WeasyPrint no carga, así que las pruebas lo simulan; las pruebas con WeasyPrint real corren en CI.
- Lint: `../.venv/Scripts/ruff.exe check .`. Migraciones: `POSTGRES_DB= ../.venv/Scripts/python.exe manage.py makemigrations --check --dry-run` debe responder `No changes detected` al final de cada tarea.
- Los commits no llevan `Co-Authored-By` ni menciones a Claude o Anthropic. No hacer commit ni push sin autorización explícita del usuario. Trabajar en la rama `feat/mantenimiento-v2`, creada **después** de integrar `feat/importar-contrasenas`.
- Repo público: las pruebas usan datos inventados.
- Interfaz en español. Todo `DateInput` de tipo `date` lleva `format="%Y-%m-%d"`.
- **Sin rojos por fechas:** "Le toca desde dd/mm/aaaa" va en ámbar (`text-bg-warning`). La pantalla principal nunca usa `bg-danger` ni la palabra "vencido" para la programación.
- Textos exactos:
  - resultados: `Bien`, `Con falla`, `No aplica`;
  - estados finales: `Operativo`, `Operativo con observaciones`, `Fuera de servicio`;
  - responsable ausente: `No asignado`;
  - tipos de acta: `Preventivo`, `Preventivo en garantía`, `Correctivo`;
  - títulos de acta: `ACTA DE MANTENIMIENTO DE EQUIPOS DE CÓMPUTO` (tipos `portatil` y `escritorio`) y `ACTA DE MANTENIMIENTO DE EQUIPOS` (los demás).
- Límites:
  - observación por punto: 150 caracteres;
  - observaciones, diagnóstico y solución: 600 cada uno;
  - fotos en el acta: 3;
  - acta firmada: `.pdf`, `.jpg`, `.jpeg` o `.png`, hasta 10 MB;
  - frecuencia por defecto: 12 meses;
  - "próximos" en Por hacer: 30 días.
- El acta va en papel **carta** (`@page { size: letter }`), siempre en **una sola página**, con `font-family: "DejaVu Sans", sans-serif`. Es la única fuente del contenedor de producción, y CI instala la misma.
- Permisos: `@requiere_permiso("mantenimiento", "lectura")` para ver y descargar, y `"escritura"` para cualquier cambio.
- Los ayudantes de prueba van en `backend/mantenimiento/ayudas_pruebas.py`, que no se descubre como prueba. Las pruebas nuevas van en archivos `backend/mantenimiento/test_*.py`.
- Toda vista nueva se reexporta en `backend/mantenimiento/views/__init__.py` con `# noqa: F401`, porque `urls.py` las usa como `views.<nombre>`. Los módulos de vistas importan los servicios como módulo (`from .. import ejecucion as servicio`) y llaman `servicio.cerrar_orden(...)`, porque hay vistas con el mismo nombre que la función de servicio.
- `OrdenMantenimiento.tecnico_asignado` (texto libre) se conserva en el modelo solo por las órdenes viejas y porque lo usa el escalamiento de Soporte. Las órdenes nuevas no lo piden ni lo llenan. El técnico es `OrdenMantenimiento.tecnico`, la cuenta que cierra. Donde haga falta mostrar un técnico, se usa `orden.tecnico.get_full_name()` y, si no hay, `orden.tecnico_asignado`.

## Review Focus

1. **La orden vieja de producción (formato 1, correctiva y cerrada, con "estado de partes").** Después de retirar los planes deben seguir abriendo su detalle, la hoja de vida, el historial, el PDF de la hoja de vida y el Excel. La cubre `test_orden_formato_anterior_sigue_visible` (Tarea 11).
2. **Un activo sin fecha de compra** (hay 1 en producción). No debe romper nada y debe salir en "Le toca" con una fecha estable. La cubre `test_sin_fecha_de_compra_le_toca_desde_su_registro` (Tarea 3).
3. **Un acta con todo al máximo:** 12 fallas con 150 caracteres cada una, 600 de observaciones, 3 fotos y 5 repuestos. Debe salir en una hoja. La cubre `test_contenido_maximo_cabe_en_una_hoja` (Tarea 7, WeasyPrint real en CI).
4. **Doble envío:** cerrar dos veces, marcar un punto en una orden ya cerrada o editar una orden cerrada. Lo esperado es un mensaje claro, nunca un 500 ni datos cambiados. Lo cubren `test_cerrar_dos_veces`, `test_no_se_marca_en_orden_cerrada` y `test_orden_cerrada_no_se_edita` (Tareas 4 y 6).
5. **Marcar "Con falla" sin observación desde el celular (HTMX).** Debe devolver la tarjeta con el error en línea y status 200, sin guardar nada. Lo cubre `test_marcar_falla_sin_observacion_htmx_muestra_error` (Tarea 4).

---

### Task 1: Partir `mantenimiento/views.py` en un paquete (sin cambios de comportamiento)

**Files:**
- Delete: `backend/mantenimiento/views.py`
- Create: `backend/mantenimiento/views/__init__.py`, `ordenes.py`, `planes.py`, `legado.py`, `reportes.py`
- Modify: `backend/mantenimiento/tests.py:444` (destino del `patch`)

**Interfaces:**
- Produces: el mismo conjunto de vistas, importables desde `mantenimiento.views`, que `urls.py` usa como `views.<nombre>`. El `__init__.py` reexporta con `# noqa: F401`, igual que `inventario/views/__init__.py`.

- [ ] **Step 1: Guardar la línea base**

Run: `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test mantenimiento core soporte notificaciones reports --noinput`
Expected: `OK`.

- [ ] **Step 2: Mover el código tal cual**

Mapeo exacto. Cada módulo importa lo que usa.
- `ordenes.py`: `FotoFormSet`, `_foto_formset`, `_parte_fields`, `lista_ordenes`, `detalle_orden`, `crear_orden`, `editar_orden`, `cerrar_orden`, `eliminar_orden`, `crear_repuesto`, `editar_repuesto`, `eliminar_repuesto`, `crear_foto`, `eliminar_foto`. Importa `_copiar_checklist_plantilla` y `_actualizar_plan_por_orden` desde `.planes`.
- `planes.py`: `ChecklistItemFormSet`, `lista_planes`, `detalle_plan`, `_formset_checklist`, `_checklist_enviado`, `crear_plan`, `editar_plan`, `toggle_plan`, `eliminar_plan`, `_guardar_checklist_items`, `_copiar_checklist_plantilla`, `_set_proxima_ejecucion`, `_actualizar_plan_por_orden`.
- `legado.py`: `estado_partes_partial`, `toggle_checklist`, `crear_item_checklist`.
- `reportes.py`: `calendario`, `calendario_eventos`, `reportar`, `_notificar_tecnico`, `hoja_de_vida_buscar`, `hoja_de_vida`, `_mantenimiento_pdf_bytes`, `orden_pdf`, `hoja_de_vida_pdf`, `reporte_activos_pdf`, `reporte_mantenimientos_pdf`.
- En `tests.py`, cambiar `patch("mantenimiento.views.encolar_email")` por `patch("mantenimiento.views.reportes.encolar_email")`.

- [ ] **Step 3: Verificar**

Run: la prueba del Step 1 y `../.venv/Scripts/ruff.exe check .`
Expected: `OK` y `All checks passed!`

- [ ] **Step 4: Commit** (solo con autorización)

```bash
git commit -am "mantenimiento: partir views.py en paquete por tema (sin cambios)"
```

---

### Task 2: Plantillas de checklist por tipo (modelo y datos iniciales)

**Files:**
- Modify: `backend/mantenimiento/models.py`
- Create: migración de esquema `backend/mantenimiento/migrations/0009_plantillachecklist_puntoplantilla.py` (con `makemigrations`) y migración de datos `0010_plantillas_iniciales.py`
- Modify: `backend/mantenimiento/admin.py` (registrar `PlantillaChecklist` con `PuntoPlantilla` en línea)
- Create: `backend/mantenimiento/ayudas_pruebas.py`
- Test: `backend/mantenimiento/test_checklists.py`

**Interfaces:**
- Produces:
  - `PlantillaChecklist(tipo_dispositivo: CharField(50, unique=True), frecuencia_meses: PositiveSmallIntegerField(default=12, validators=[MinValueValidator(1)]), fecha_creacion, fecha_actualizacion)`.
    - Tiene `__str__`.
    - `get_tipo_dispositivo_display()` usa `inventario.models._ver_tipo`.
    - `ordering = ["tipo_dispositivo"]`.
  - `PuntoPlantilla(plantilla: FK→PlantillaChecklist CASCADE related_name="puntos", seccion: CharField(60), descripcion: CharField(150), posicion: PositiveIntegerField(default=0), aplica_en_garantia: BooleanField(default=False), activo: BooleanField(default=True))`, con `ordering = ["posicion", "id"]`.
  - `SECCIONES_SUGERIDAS = ["Hardware", "Limpieza", "Mantenimiento lógico"]` en `models.py`.
  - `ayudas_pruebas.py`:
    - `crear_usuario(rol="tecnico", **kw)`
    - `crear_pc(serial="SN-PC-1", tipo="portatil", compra=None, meses=None, **kw) -> Activo` (por defecto marca "HP", modelo "ProBook" y estado "disponible"; `kw` sobrescribe esos valores, por ejemplo `estado="dado_de_baja"`)
    - `asignar(activo, nombre="Marta López Gómez", documento="200300400", cargo="Contadora", area="Finanzas") -> Asignacion` (crea el `usuarios.Usuario`, con correo inventado `marta@example.com`)

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_checklists.py`)

```python
from django.db import IntegrityError
from django.test import TestCase

from mantenimiento.models import PlantillaChecklist

PORTATIL = [
    ("Hardware", "Desarme del equipo", False), ("Hardware", "Pantalla", False),
    ("Hardware", "Bisagras", False), ("Hardware", "Batería", False),
    ("Limpieza", "Limpieza externa", True), ("Limpieza", "Limpieza interna", False),
    ("Limpieza", "Limpieza de puertos", False),
    ("Mantenimiento lógico", "Actualizaciones de Windows", True), ("Mantenimiento lógico", "Antivirus", True),
    ("Mantenimiento lógico", "Archivos temporales", True), ("Mantenimiento lógico", "Estado del disco", True),
    ("Mantenimiento lógico", "Programas de inicio", True),
]
ESCRITORIO = [p for p in PORTATIL if p[1] not in ("Pantalla", "Bisagras", "Batería")]


def _puntos(tipo):
    plantilla = PlantillaChecklist.objects.get(tipo_dispositivo=tipo)
    return [(p.seccion, p.descripcion, p.aplica_en_garantia) for p in plantilla.puntos.all()]


class PlantillasInicialesTests(TestCase):
    def test_portatil(self):
        self.assertEqual(_puntos("portatil"), PORTATIL)
        self.assertEqual(PlantillaChecklist.objects.get(tipo_dispositivo="portatil").frecuencia_meses, 12)

    def test_escritorio(self):
        self.assertEqual(_puntos("escritorio"), ESCRITORIO)

    def test_un_checklist_por_tipo(self):
        with self.assertRaises(IntegrityError):
            PlantillaChecklist.objects.create(tipo_dispositivo="portatil")
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `... manage.py test mantenimiento.test_checklists --noinput`
Expected: ERROR `ImportError: cannot import name 'PlantillaChecklist'`.

- [ ] **Step 3: Implementar**

- Escribir los modelos y correr `makemigrations mantenimiento` para generar la 0009.
- Migración 0010 (`RunPython`, con reversa que borra las dos plantillas): crea `portatil` y `escritorio` con los puntos de la tabla de la §B2 del spec. La posición es el índice en la lista, empezando en 0. La lista va definida **dentro** de la migración; no se importa de `models`.

- [ ] **Step 4: Correr y ver que pasan**

Run: `... manage.py test mantenimiento.test_checklists mantenimiento --noinput`
Expected: `OK`.

- [ ] **Step 5: Commit** (solo con autorización)

```bash
git add backend/mantenimiento
git commit -m "mantenimiento: plantillas de checklist por tipo con datos iniciales"
```

---

### Task 3: Programación por equipo (lógica)

**Files:**
- Modify: `backend/mantenimiento/models.py`:
  - `ProgramacionMantenimiento`;
  - en `OrdenMantenimiento`, `en_garantia` y `formato`;
  - las constantes `FORMATO_ANTERIOR = 1` y `FORMATO_ACTUAL = 2`.
- Create: migración `0011` (esquema + `RunPython` que pone `formato=1` a **todas las órdenes existentes**, con reversa no-op)
- Create: `backend/mantenimiento/programacion.py`
- Test: `backend/mantenimiento/test_programacion.py`

**Interfaces:**
- Consumes: `PlantillaChecklist` (Tarea 2), `inventario.models._add_months` y `Activo.fecha_vencimiento_garantia`.
- Produces:
  - `ProgramacionMantenimiento(activo: OneToOneField("inventario.Activo", CASCADE, related_name="programacion_mantenimiento"), fecha_programada: DateField(null=True, blank=True), fecha_actualizacion)`.
  - En `OrdenMantenimiento`: `en_garantia: BooleanField(default=False)` y `formato: PositiveSmallIntegerField(default=FORMATO_ACTUAL)`.
  - En `programacion.py`:
    - `DIAS_PROXIMOS = 30`.
    - `@dataclass(frozen=True) class Situacion`: `activo: Activo`, `estado: str` (`"programado" | "le_toca" | "en_garantia" | "al_dia"`), `le_toca_desde: date`, `fecha_programada: date | None`, `vencimiento_garantia: date | None`, `ultimo: OrdenMantenimiento | None` (el último cerrado, de cualquier tipo).
    - `activos_programables() -> QuerySet[Activo]`: los tipos con `PlantillaChecklist`, sin los `dado_de_baja`.
    - `ultimo_preventivo_completo(activo) -> OrdenMantenimiento | None`: `tipo="preventivo"`, `estado="cerrada"`, `en_garantia=False` y la `fecha_cierre` más reciente.
    - `fecha_le_toca(activo) -> date`.
    - `situacion(activo, hoy: date | None = None) -> Situacion`.
    - `tablero(hoy: date | None = None) -> dict` con las claves `por_hacer`, `en_garantia` y `al_dia` (listas de `Situacion`) y `conteos` (dict con `programado`, `le_toca`, `en_garantia` y `al_dia`).
    - `proximo_preventivo(orden) -> date | None`.

Reglas (spec §B4):
- `fecha_le_toca`:
  - si hay un preventivo completo, es su `fecha_cierre` más `plantilla.frecuencia_meses`;
  - si no, el vencimiento de la garantía;
  - si no hay garantía calculable, `timezone.localdate(activo.fecha_creacion)`. Es la implementación de "le toca desde hoy" con una fecha que no cambia cada día.
- Estado: es `programado` si hay `fecha_programada`. Si no, `le_toca` si `le_toca_desde <= hoy`. Si no, `en_garantia` si hay vencimiento, `hoy <= vencimiento` y no hay preventivo completo. En cualquier otro caso, `al_dia`.
- `por_hacer` = programado + le_toca + los al_dia con `le_toca_desde <= hoy + 30 días`. Se ordena por `(fecha_programada or le_toca_desde, serial)`.
- La lista `al_dia` excluye a los próximos, que ya salen en por hacer. `en_garantia` se ordena por vencimiento. `conteos` cuenta cada estado una vez; los próximos cuentan como `al_dia`.
- `proximo_preventivo`: `None` si no es preventivo. Si fue en garantía, el vencimiento de la garantía. Si no, `fecha_cierre` más la frecuencia.

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_programacion.py`; `HOY = date(2026, 10, 23)`)

```python
class ReglaLeTocaTests(TestCase):
    def test_en_garantia_no_le_toca_hasta_que_vence(self):
        pc = crear_pc(compra=date(2025, 10, 1), meses=24)
        s = situacion(pc, HOY)
        self.assertEqual((s.estado, s.le_toca_desde), ("en_garantia", date(2027, 10, 1)))

    def test_le_toca_desde_el_vencimiento_si_nunca_tuvo_preventivo(self):
        s = situacion(crear_pc(compra=date(2023, 1, 10), meses=12), HOY)
        self.assertEqual((s.estado, s.le_toca_desde), ("le_toca", date(2024, 1, 10)))

    def test_despues_del_preventivo_completo_cuenta_desde_el_cierre(self):
        pc = crear_pc(compra=date(2023, 1, 10), meses=12)
        _cerrada(pc, "preventivo", date(2026, 3, 5), en_garantia=False)
        s = situacion(pc, HOY)
        self.assertEqual((s.estado, s.le_toca_desde), ("al_dia", date(2027, 3, 5)))

    def test_usa_la_frecuencia_de_la_plantilla(self):
        PlantillaChecklist.objects.filter(tipo_dispositivo="portatil").update(frecuencia_meses=6)
        pc = crear_pc(compra=date(2023, 1, 10), meses=12)
        _cerrada(pc, "preventivo", date(2026, 3, 5), en_garantia=False)
        self.assertEqual(situacion(pc, HOY).le_toca_desde, date(2026, 9, 5))

    def test_preventivo_en_garantia_y_correctivo_no_mueven_la_fecha(self):
        pc = crear_pc(compra=date(2025, 10, 1), meses=24)
        _cerrada(pc, "preventivo", date(2026, 5, 1), en_garantia=True)
        _cerrada(pc, "correctivo", date(2026, 6, 1))
        self.assertEqual(situacion(pc, HOY).le_toca_desde, date(2027, 10, 1))

    def test_sin_fecha_de_compra_le_toca_desde_su_registro(self):
        pc = crear_pc(compra=None)
        Activo.objects.filter(pk=pc.pk).update(fecha_creacion=datetime(2026, 1, 15, 12, tzinfo=dt_timezone.utc))
        pc.refresh_from_db()
        s = situacion(pc, HOY)
        self.assertEqual((s.estado, s.le_toca_desde), ("le_toca", date(2026, 1, 15)))

    def test_programado_gana_sobre_los_demas_estados(self):
        pc = crear_pc(compra=date(2025, 10, 1), meses=24)
        ProgramacionMantenimiento.objects.create(activo=pc, fecha_programada=date(2026, 11, 5))
        self.assertEqual(situacion(pc, HOY).estado, "programado")

    def test_ultimo_es_el_ultimo_cerrado_de_cualquier_tipo(self):
        pc = crear_pc(compra=date(2023, 1, 10), meses=12)
        _cerrada(pc, "preventivo", date(2026, 3, 5))
        correctivo = _cerrada(pc, "correctivo", date(2026, 8, 1))
        self.assertEqual(situacion(pc, HOY).ultimo, correctivo)


class TableroTests(TestCase):
    def test_solo_tipos_con_checklist_y_sin_dados_de_baja(self):
        incluidos = {crear_pc("A").pk, crear_pc("B", tipo="escritorio").pk}
        crear_pc("C", tipo="celular")
        crear_pc("D", estado="dado_de_baja")
        self.assertEqual(set(activos_programables().values_list("pk", flat=True)), incluidos)

    def test_por_hacer_incluye_proximos_30_dias_y_ordena(self):
        crear_pc("A", compra=date(2023, 1, 10), meses=12)                     # le toca desde 2024
        b = crear_pc("B", compra=date(2025, 10, 1), meses=24)
        ProgramacionMantenimiento.objects.create(activo=b, fecha_programada=date(2026, 11, 1))
        c = crear_pc("C", compra=date(2020, 1, 1), meses=12)
        _cerrada(c, "preventivo", date(2025, 11, 10))                         # le toca 2026-11-10
        d = crear_pc("D", compra=date(2020, 1, 1), meses=12)
        _cerrada(d, "preventivo", date(2026, 5, 1))                           # le toca 2027-05-01
        crear_pc("E", compra=date(2025, 10, 1), meses=24)                     # en garantía
        t = tablero(HOY)
        self.assertEqual([s.activo.serial for s in t["por_hacer"]], ["A", "B", "C"])
        self.assertEqual([s.activo.serial for s in t["al_dia"]], ["D"])
        self.assertEqual([s.activo.serial for s in t["en_garantia"]], ["E"])
        self.assertEqual(t["conteos"], {"programado": 1, "le_toca": 1, "en_garantia": 1, "al_dia": 2})


class ProximoPreventivoTests(TestCase):
    def test_completo_en_garantia_y_correctivo(self):
        pc = crear_pc(compra=date(2025, 10, 1), meses=24)
        self.assertEqual(proximo_preventivo(_cerrada(pc, "preventivo", date(2026, 10, 23))), date(2027, 10, 23))
        self.assertEqual(proximo_preventivo(_cerrada(pc, "preventivo", date(2026, 5, 1), en_garantia=True)), date(2027, 10, 1))
        self.assertIsNone(proximo_preventivo(_cerrada(pc, "correctivo", date(2026, 5, 1))))

    def test_orden_nueva_es_formato_actual(self):
        self.assertEqual(_cerrada(crear_pc(), "correctivo", HOY).formato, 2)
```

`_cerrada(activo, tipo, fecha_cierre, en_garantia=False)` es un ayudante local que crea `OrdenMantenimiento(estado="cerrada", fecha_apertura=fecha_cierre, fecha_cierre=fecha_cierre, …)`.

- [ ] **Step 2: Correr y ver que fallan** → `ImportError` de `mantenimiento.programacion`.

- [ ] **Step 3: Implementar** los modelos, la migración 0011 y `programacion.py` con las reglas de arriba.

- [ ] **Step 4: Correr y ver que pasan**

Run: `... manage.py test mantenimiento --noinput` → `OK`.

- [ ] **Step 5: Commit** (solo con autorización): `"mantenimiento: programación por equipo (garantía + ciclo desde el último preventivo)"`.

---

### Task 4: Iniciar un preventivo y llenar el checklist

**Files:**
- Modify: `backend/mantenimiento/models.py`: en `ChecklistItem`, `seccion`, `resultado` y `observacion`; las constantes `RESULTADOS_PUNTO = [("bien", "Bien"), ("falla", "Con falla"), ("na", "No aplica")]` y `LIMITE_OBS_PUNTO = 150`. Va con su migración 0012.
- Create: `backend/mantenimiento/ejecucion.py`
- Create: `backend/mantenimiento/views/ejecucion.py` (`nuevo`, `iniciar_preventivo`, `marcar_punto`)
- Modify: `backend/mantenimiento/forms.py` (`NuevoMantenimientoForm`), `urls.py` y `views/__init__.py`
- Create: `templates/mantenimiento/nuevo.html` y `templates/mantenimiento/partials/checklist_ejecucion.html`
- Modify: `templates/mantenimiento/detalle_orden.html` (incluye la tarjeta del checklist si `orden.formato == 2` y es preventivo)
- Modify: `backend/inventario/templates/inventario/partials/tabla.html:104` (el enlace "Documentar mantenimiento" pasa a `{% url 'mantenimiento:nuevo' %}?activo={{ a.pk }}`)
- Modify: `backend/core/tests.py` (agrega `"mantenimiento:nuevo"` a `RUTAS`)
- Test: `backend/mantenimiento/test_ejecucion.py`

**Interfaces:**
- Consumes: `PlantillaChecklist` y `PuntoPlantilla` (Tarea 2), `OrdenMantenimiento.en_garantia` y `formato` (Tarea 3), y `services.snapshot_software_ocs`.
- Produces:
  - `ChecklistItem`: `seccion = CharField(60, blank=True)`, `resultado = CharField(10, choices=RESULTADOS_PUNTO, blank=True)` y `observacion = CharField(LIMITE_OBS_PUNTO, blank=True)`. Los campos `plan` y `completado` siguen existiendo hasta la Tarea 11.
  - En `ejecucion.py`:
    - `plantilla_para(activo) -> PlantillaChecklist | None`.
    - `esta_en_garantia(activo, hoy: date) -> bool`: el vencimiento existe y `hoy <= vencimiento`.
    - `iniciar_preventivo(activo, usuario, hoy: date | None = None) -> OrdenMantenimiento`, que lanza `ValidationError` con exactamente uno de estos mensajes:
      - `"El equipo está dado de baja."`
      - `"No hay checklist para este tipo de equipo."`
      - `"Este equipo ya tiene un mantenimiento preventivo abierto."` (cuando hay uno `abierta` o `en_proceso`)
    - `marcar_punto(item, resultado: str, observacion: str = "") -> ChecklistItem`, que lanza `ValidationError` con:
      - `"El mantenimiento ya está cerrado."`
      - `"Resultado no válido."`
      - `"La observación no puede pasar de 150 caracteres."`
      - `"Explica la falla en la observación."`
  - URLs:
    - `mantenimiento:nuevo` → `nuevo/` (GET formulario; en POST, preventivo inicia y correctivo redirige a `crear_orden?activo=<pk>`).
    - `mantenimiento:iniciar_preventivo` → `iniciar/<int:activo_pk>/` (solo POST).
    - `mantenimiento:marcar_punto` → `puntos/<int:pk>/marcar/` (solo POST; con `HX-Request` devuelve `partials/checklist_ejecucion.html`).
  - Un campo POST opcional `volver`: si es seguro (`url_has_allowed_host_and_scheme`), los errores de `iniciar_preventivo` redirigen ahí; si no, a `mantenimiento:nuevo`.

`iniciar_preventivo` crea la orden con:
- `tipo="preventivo"`, `estado="en_proceso"`, `fecha_apertura=hoy`, `formato=2`;
- `en_garantia=esta_en_garantia(...)`;
- `software_snapshot`: los nombres que devuelva `snapshot_software_ocs(activo)`.

No llena `tecnico_asignado`.

Después copia los `PuntoPlantilla` con `activo=True` (y además con `aplica_en_garantia=True` si el equipo está en garantía) como `ChecklistItem(orden, seccion, descripcion, posicion)`, sin resultado.

La tarjeta del checklist agrupa los puntos por sección. Por cada punto muestra tres botones grandes (`Bien` / `Con falla` / `No aplica`) con `hx-post` y un campo de observación que se envía con el botón. Muestra el progreso "N de M marcados" y el error en línea si `marcar_punto` lo rechaza. Si la orden está cerrada o el usuario solo tiene lectura, se muestra en modo lectura: etiquetas `BIEN` / `FALLA` / `N/A` con la observación debajo.

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_ejecucion.py`; `snapshot_software_ocs` se simula con `patch("mantenimiento.ejecucion.snapshot_software_ocs", return_value=[{"name": "Office"}])`)

```python
class IniciarPreventivoTests(TestCase):
    def test_fuera_de_garantia_copia_todos_los_puntos(self):
        orden = iniciar_preventivo(crear_pc(compra=date(2023, 1, 1), meses=12), crear_usuario(), HOY)
        self.assertEqual((orden.tipo, orden.estado, orden.en_garantia, orden.formato), ("preventivo", "en_proceso", False, 2))
        self.assertEqual([(i.seccion, i.descripcion, i.resultado) for i in orden.checklist_items.all()],
                         [(s, d, "") for s, d, _ in PORTATIL])
        self.assertEqual(orden.software_snapshot, ["Office"])

    def test_en_garantia_copia_solo_los_que_aplican(self):
        orden = iniciar_preventivo(crear_pc(compra=date(2026, 1, 1), meses=24), crear_usuario(), HOY)
        self.assertTrue(orden.en_garantia)
        self.assertEqual([i.descripcion for i in orden.checklist_items.all()],
                         ["Limpieza externa", "Actualizaciones de Windows", "Antivirus",
                          "Archivos temporales", "Estado del disco", "Programas de inicio"])

    def test_no_permite_dos_preventivos_abiertos(self):
        pc, u = crear_pc(), crear_usuario()
        iniciar_preventivo(pc, u, HOY)
        with self.assertRaisesMessage(ValidationError, "Este equipo ya tiene un mantenimiento preventivo abierto."):
            iniciar_preventivo(pc, u, HOY)

    def test_tipo_sin_checklist_no_inicia(self):
        with self.assertRaisesMessage(ValidationError, "No hay checklist para este tipo de equipo."):
            iniciar_preventivo(crear_pc(tipo="celular"), crear_usuario(), HOY)

    def test_cambiar_la_plantilla_no_afecta_ordenes_iniciadas(self):
        orden = iniciar_preventivo(crear_pc(), crear_usuario(), HOY)
        PuntoPlantilla.objects.filter(descripcion="Pantalla").update(descripcion="Pantalla y marco")
        self.assertTrue(orden.checklist_items.filter(descripcion="Pantalla").exists())


class MarcarPuntoTests(TestCase):
    def setUp(self):
        self.orden = iniciar_preventivo(crear_pc(), crear_usuario(), HOY)
        self.item = self.orden.checklist_items.get(descripcion="Bisagras")

    def test_falla_exige_observacion(self):
        with self.assertRaisesMessage(ValidationError, "Explica la falla en la observación."):
            marcar_punto(self.item, "falla", "  ")
        marcar_punto(self.item, "falla", "Bisagra izquierda floja")
        self.item.refresh_from_db()
        self.assertEqual((self.item.resultado, self.item.observacion), ("falla", "Bisagra izquierda floja"))

    def test_observacion_maximo_150(self):
        with self.assertRaisesMessage(ValidationError, "La observación no puede pasar de 150 caracteres."):
            marcar_punto(self.item, "bien", "x" * 151)

    def test_no_se_marca_en_orden_cerrada(self):
        OrdenMantenimiento.objects.filter(pk=self.orden.pk).update(estado="cerrada")
        self.item.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "El mantenimiento ya está cerrado."):
            marcar_punto(self.item, "bien")


class VistasEjecucionTests(TestCase):
    # Pruebas con el cliente: tecnico (escritura) y lectura.
    def test_iniciar_redirige_al_detalle(self): ...          # POST → 302 a detalle_orden de la orden nueva
    def test_iniciar_requiere_escritura(self): ...           # rol lectura → redirect a core:dashboard, sin órdenes
    def test_iniciar_con_error_vuelve_a_volver_seguro(self): ...  # 2.º inicio con volver="/mantenimiento/" → 302 a "/mantenimiento/" + mensaje
    def test_volver_externo_se_ignora(self): ...             # volver="https://malo.example" → 302 a mantenimiento:nuevo
    def test_marcar_punto_htmx_devuelve_la_tarjeta(self): ...  # HX-Request, resultado=bien → 200, contiene "1 de 12 marcados"
    def test_marcar_falla_sin_observacion_htmx_muestra_error(self): ...  # 200, contiene "Explica la falla en la observación.", resultado sigue ""
    def test_nuevo_preventivo_crea_y_redirige(self): ...     # POST activo+tipo=preventivo → 302 al detalle
    def test_nuevo_correctivo_redirige_al_formulario(self): ...  # POST tipo=correctivo → 302 a crear_orden?activo=<pk>
```

En las pruebas de vistas, el `...` se reemplaza por el cuerpo correspondiente; el comentario de cada una fija la aserción.

- [ ] **Step 2: Correr y ver que fallan** → `ImportError` de `mantenimiento.ejecucion`.
- [ ] **Step 3: Implementar** el modelo, la migración, `ejecucion.py`, las vistas, el formulario, las URLs y las plantillas.
- [ ] **Step 4: Correr y ver que pasan**

Run: `... manage.py test mantenimiento core.tests.SmokeVistasTests inventario --noinput` → `OK`.

- [ ] **Step 5: Commit** (solo con autorización): `"mantenimiento: iniciar preventivo con checklist copiado y marcar puntos (HTMX)"`.

---

### Task 5: Pantalla principal y programar fecha

**Files:**
- Create: `backend/mantenimiento/views/tablero.py` (`inicio` y `programar`)
- Modify: `backend/mantenimiento/forms.py` (`ProgramarForm`), `urls.py` y `views/__init__.py`
- Create: `templates/mantenimiento/inicio.html`, `partials/tabla_programacion.html` y `partials/fila_programacion.html`
- Modify:
  - `templates/base.html:73`: el menú apunta a `mantenimiento:inicio`;
  - `lista_ordenes.html`: el título pasa a "Historial", el enlace "Planes" se quita (los planes desaparecen en la Tarea 11) y se agrega el filtro `fallas=1`;
  - `views/ordenes.py`: `lista_ordenes` acepta `fallas=1`, que filtra `tipo="correctivo"` y `estado__in=["reportada", "abierta", "en_proceso"]`;
  - los breadcrumbs de `detalle_orden.html` llevan "Mantenimiento" → `inicio`.
- Modify: `backend/core/tests.py` (`RUTAS` + `"mantenimiento:inicio"`)
- Test: `backend/mantenimiento/test_tablero.py`

**Interfaces:**
- Consumes: `tablero()` y `situacion()` (Tarea 3), y `mantenimiento:iniciar_preventivo` con `volver` (Tarea 4).
- Produces:
  - `mantenimiento:inicio` → `""`, con la pestaña en `?tab=por_hacer|en_garantia|al_dia` (por defecto `por_hacer`).
  - `mantenimiento:lista_ordenes` pasa de `""` a `historial/`.
  - `mantenimiento:programar` → `programar/<int:activo_pk>/` (POST con `fecha_programada`; vacío la borra). Con HTMX devuelve `partials/tabla_programacion.html` de la pestaña indicada en el POST (`tab`); sin HTMX redirige a `inicio?tab=…`.
  - `ProgramarForm`: `fecha_programada = DateField(required=False, widget=DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}, format="%Y-%m-%d"))`.

Contenido según el boceto `programacion.html`:
- tarjetas Le toca, Programados, En garantía y Al día, con los `conteos`;
- pestañas Por hacer (n), En garantía (n), Al día (n), Historial (→ `lista_ordenes`) y Fallas reportadas (n) (→ `lista_ordenes?fallas=1`);
- columnas Equipo (tipo, marca y modelo, serial, N° interno), Responsable (la asignación activa o `No asignado`), Último mantenimiento (fecha y tipo, o `Nunca`) y Estado:
  - `Le toca desde dd/mm/aaaa` en ámbar;
  - `Programado dd/mm/aaaa` en azul;
  - `En garantía hasta dd/mm/aaaa` en morado;
  - `Le toca el dd/mm/aaaa` en gris;
- acciones solo con escritura: "Programar" o "Cambiar fecha" (formulario en línea dentro de `<details>`) e "Iniciar" (POST a `iniciar_preventivo` con `volver`);
- botones: Calendario, Hoja de vida y "+ Mantenimiento" (→ `nuevo`). El botón "Checklists" lo agrega la Tarea 9.

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_tablero.py`; las fechas se arman relativas a `timezone.localdate()`)

```python
class InicioTests(TestCase):
    def test_por_hacer_muestra_los_que_les_toca_y_no_los_de_garantia(self): ...  # contiene serial le_toca, no el en garantía
    def test_pestana_en_garantia(self): ...                     # ?tab=en_garantia contiene el en garantía
    def test_tarjetas_cuentan_por_estado(self): ...             # resp.context["conteos"] == {...}
    def test_sin_rojo_de_vencido(self): ...                     # contiene "Le toca desde"; no contiene "bg-danger" ni "encid"
    def test_lectura_no_ve_programar_ni_iniciar(self): ...      # rol lectura: assertNotContains "Programar" / "Iniciar"
    def test_responsable_o_no_asignado(self): ...               # con asignar(): "Marta López Gómez"; sin: "No asignado"


class ProgramarTests(TestCase):
    def test_programar_y_quitar_fecha(self): ...                # POST fecha → guardada; POST "" → None
    def test_programar_requiere_escritura(self): ...            # lectura → redirect dashboard; no crea ProgramacionMantenimiento
    def test_fecha_invalida_no_guarda(self): ...                # "2026-13-40" → mensaje de error; sin cambios
    def test_htmx_devuelve_la_tabla(self): ...                  # HX-Request → 200 con el serial y "Programado"


class HistorialTests(TestCase):
    def test_fallas_reportadas_filtra(self): ...                # ?fallas=1 muestra correctivo reportada, no cerrada
```

- [ ] **Step 2: Correr y ver que fallan** → `NoReverseMatch: 'inicio'`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr y ver que pasan**

Run: `... manage.py test mantenimiento core --noinput` → `OK`. Ajustar las pruebas viejas que usen `reverse("mantenimiento:lista_ordenes")` solo si comparan la URL literal.

- [ ] **Step 5: Commit** (solo con autorización): `"mantenimiento: pantalla principal por equipo y programar fecha"`.

---

### Task 6: Cerrar y reabrir; nombre y cargo del técnico

**Files:**
- Modify: `backend/mantenimiento/models.py`, con su migración 0013. En `OrdenMantenimiento`:
  - `tecnico` (FK user, `SET_NULL`, `null`, `related_name="mantenimientos_cerrados"`);
  - `estado_final` (`CharField(30, choices=ESTADOS_FINALES, blank=True)`);
  - `observaciones` (`TextField(blank=True)`);
  - `datos_acta` (`JSONField(default=dict, blank=True)`);
  - `acta_firmada` (`FileField(upload_to="mantenimiento/actas/", null=True, blank=True)`);
  - `acta_firmada_desactualizada` (`BooleanField(default=False)`);
  - las constantes `ESTADOS_FINALES = [("operativo", "Operativo"), ("operativo_obs", "Operativo con observaciones"), ("fuera_servicio", "Fuera de servicio")]` y `LIMITE_TEXTO_ACTA = 600`.
- Modify: `backend/accounts/models.py`, con su migración `0003`: `cargo = CharField(max_length=150, blank=True)`.
- Modify: `backend/mantenimiento/ejecucion.py`, `forms.py` (`CerrarOrdenForm`) y `views/ejecucion.py` (`cerrar_orden` y `reabrir_orden`). Quitar el `cerrar_orden` viejo de `views/ordenes.py`. En `editar_orden`, una orden cerrada redirige al detalle con un aviso.
- Create: `templates/mantenimiento/cerrar.html`
- Modify: `detalle_orden.html`: "Cerrar" pasa a ser un enlace a la página de cierre; se agrega "Reabrir" (POST) si está cerrada; se muestran el estado final, las observaciones y el técnico.
- Modify: `backend/administracion/forms.py`:
  - `CuentaForm.Meta.fields = ["username", "first_name", "last_name", "cargo", "email", "rol"]`;
  - `CuentaRolForm.Meta.fields = ["first_name", "last_name", "cargo", "rol"]`, con labels "Nombres", "Apellidos" y "Cargo".
- Modify: `administracion/views.py::cambiar_rol_cuenta`, que también guarda nombres y cargo. Su plantilla `cuenta_rol.html` pasa a titularse "Editar cuenta", y `cuenta_form.html` muestra los campos nuevos.
- Test: `backend/mantenimiento/test_cierre.py` y `backend/administracion/tests.py`

**Interfaces:**
- Consumes: `proximo_preventivo` (Tarea 3) y los `ChecklistItem` con resultado (Tarea 4).
- Produces (en `ejecucion.py`):
  - `campos_equipo(activo) -> list[list[str]]`: pares `[etiqueta, valor]`; un valor vacío se muestra como `"—"`.
    - Comunes: `Equipo` (`get_tipo_dispositivo_display()`), `Marca/modelo`, `Serial` y `N° interno`.
    - `portatil` y `escritorio` agregan `Nombre`, `Procesador`, `RAM`, `Disco` (capacidad y tipo) y `S.O.`, `IP`.
    - `celular`: `IMEI`, `Línea`, `Operador` y `Almacenamiento`.
    - `telefono_fijo`: `Extensión` y `Línea`.
    - `monitor`: `Pulgadas` y `Resolución`.
    - Todos terminan en `Ubicación`.
  - `datos_para_acta(orden, usuario) -> dict` con las claves:
    - `tipo_acta`, `titulo`, `campos`;
    - `garantia`: `"Hasta dd/mm/aaaa"` si `fecha_cierre <= vencimiento`, `"Vencida dd/mm/aaaa"` si ya pasó, o `"Sin dato"` si no hay vencimiento;
    - `proximo`: `"dd/mm/aaaa"` o `""`;
    - `responsable`: `{"nombre", "documento", "cargo", "area"}` o `None`;
    - `tecnico`: `{"nombre", "cargo"}`.
  - `errores_para_cerrar(orden, *, fecha_cierre, estado_final, observaciones, diagnostico="", acciones="") -> list[str]`. Mensajes exactos, en este orden:
    - `"El mantenimiento ya está cerrado."` (si ya lo está, solo devuelve este)
    - `"La fecha de cierre no puede ser futura."`
    - `"La fecha de cierre no puede ser anterior a la apertura."`
    - `"Elige el estado final del equipo."`
    - `"Las observaciones no pueden pasar de 600 caracteres."`
    - solo en preventivo de formato 2: `f"Quedan puntos del checklist sin marcar ({n})."` y `"Cada falla necesita su observación."`
    - solo en correctivo: `"Escribe el diagnóstico."`, `"Escribe la solución o las acciones realizadas."` y los límites de 600 (`"El diagnóstico no puede pasar de 600 caracteres."` / `"La solución no puede pasar de 600 caracteres."`)
  - `cerrar_orden(orden, usuario, *, fecha_cierre, estado_final, observaciones, diagnostico="", acciones="") -> None`: lanza `ValidationError(errores)`. Pone `estado="cerrada"`, `tecnico=usuario` y, ya con `fecha_cierre` asignada, `datos_acta`. Si es preventivo, deja `fecha_programada=None` en la `ProgramacionMantenimiento` del activo.
  - `reabrir_orden(orden) -> None`: `estado="en_proceso"`, `fecha_cierre=None` y `datos_acta={}`. Si hay `acta_firmada`, pone `acta_firmada_desactualizada=True`.
- URLs: `mantenimiento:cerrar_orden` (GET formulario / POST) y `mantenimiento:reabrir_orden` → `ordenes/<int:pk>/reabrir/` (POST).
- `CerrarOrdenForm(*args, orden, pedir_datos_tecnico: bool, **kwargs)` tiene `fecha_cierre` (inicial hoy), `estado_final` (radio), `observaciones` (`max_length=600`) y, si es correctivo, `diagnostico` y `acciones` (`max_length=600`). Si `pedir_datos_tecnico`, agrega `first_name`, `last_name` y `cargo`, obligatorios, que se guardan en `request.user` antes de cerrar. `pedir_datos_tecnico = not request.user.get_full_name().strip()`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
class CerrarTests(TestCase):
    def setUp(self):
        self.tecnico = crear_usuario(first_name="Ana", last_name="Técnica", cargo="Analista de Sistemas")
        self.pc = crear_pc(compra=date(2023, 1, 1), meses=12, nombre_equipo="PT-12", ip_equipo="192.168.1.57")
        self.orden = iniciar_preventivo(self.pc, self.tecnico, HOY)   # con snapshot_software_ocs simulado

    def _marcar_todo(self, resultado="bien"):
        for item in self.orden.checklist_items.all():
            marcar_punto(item, resultado, "x" if resultado == "falla" else "")

    def _cerrar(self, **kw):
        datos = {"fecha_cierre": HOY, "estado_final": "operativo", "observaciones": ""} | kw
        cerrar_orden(self.orden, self.tecnico, **datos)

    def test_no_cierra_con_puntos_pendientes(self):
        with self.assertRaisesMessage(ValidationError, "Quedan puntos del checklist sin marcar (12)."):
            self._cerrar()

    def test_cierra_y_congela_datos_del_acta(self):
        asignar(self.pc)
        self._marcar_todo()
        self._cerrar()
        self.orden.refresh_from_db()
        self.assertEqual((self.orden.estado, self.orden.tecnico), ("cerrada", self.tecnico))
        d = self.orden.datos_acta
        self.assertEqual(d["tipo_acta"], "Preventivo")
        self.assertEqual(d["titulo"], "ACTA DE MANTENIMIENTO DE EQUIPOS DE CÓMPUTO")
        self.assertEqual(d["responsable"], {"nombre": "Marta López Gómez", "documento": "200300400", "cargo": "Contadora", "area": "Finanzas"})
        self.assertEqual(d["tecnico"], {"nombre": "Ana Técnica", "cargo": "Analista de Sistemas"})
        self.assertIn(["IP", "192.168.1.57"], d["campos"])
        self.assertEqual(d["proximo"], "23/10/2027")
        Activo.objects.filter(pk=self.pc.pk).update(ip_equipo="10.0.0.9")
        self.orden.refresh_from_db()
        self.assertIn(["IP", "192.168.1.57"], self.orden.datos_acta["campos"])

    def test_sin_responsable_queda_none(self): ...       # sin asignar() → d["responsable"] is None
    def test_cerrar_limpia_la_fecha_programada(self): ... # ProgramacionMantenimiento con fecha → None tras cerrar
    def test_en_garantia_tipo_acta_y_proximo(self): ...  # pc en garantía → "Preventivo en garantía", proximo = vencimiento
    def test_cerrar_dos_veces(self): ...                 # 2.º cerrar → "El mantenimiento ya está cerrado."
    def test_fecha_de_cierre_futura(self): ...           # HOY + 1 → "La fecha de cierre no puede ser futura."
    def test_observaciones_maximo_600(self): ...
    def test_correctivo_exige_diagnostico_y_solucion(self): ...
    def test_reabrir_marca_acta_firmada_desactualizada(self): ...  # con acta_firmada → reabrir → en_proceso, datos_acta {}, desactualizada True


class CamposEquipoTests(TestCase):
    def test_por_tipo(self): ...   # portatil incluye "Procesador"; celular incluye "IMEI"; tipo "Diadema" solo comunes + "Ubicación"


class VistaCerrarTests(TestCase):
    def test_pide_nombre_y_cargo_si_la_cuenta_no_tiene_nombre(self): ...  # GET contiene name="first_name"; POST los guarda y cierra
    def test_no_pide_nombre_si_ya_lo_tiene(self): ...
    def test_errores_se_muestran_sin_cerrar(self): ...   # checklist incompleto → 200 con el mensaje; sigue en_proceso
    def test_orden_cerrada_no_se_edita(self): ...        # GET editar_orden de cerrada → redirect al detalle
    def test_reabrir_requiere_escritura(self): ...
```

En `administracion/tests.py`: `test_crear_cuenta_con_nombre_y_cargo` y `test_editar_cuenta_cambia_nombre_cargo_y_rol`.

- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr y ver que pasan**

Run: `... manage.py test mantenimiento administracion accounts --noinput` → `OK`.

- [ ] **Step 5: Commit** (solo con autorización): `"mantenimiento: cerrar con validación y datos congelados del acta; reabrir"`.

---

### Task 7: Acta PDF de una hoja carta

**Files:**
- Modify: `backend/administracion/models.py`, con su migración `0004`: `acta_mant_codigo = CharField("Código del acta de mantenimiento", max_length=30, blank=True)` y `acta_mant_version = CharField("Versión del acta de mantenimiento", max_length=10, blank=True)`. Se agregan a `ConfiguracionForm` y a `configuracion_form.html`, en un fieldset nuevo "Acta de mantenimiento".
- Modify: `backend/mantenimiento/models.py`, con su migración 0014: `FotoMantenimiento.en_acta = BooleanField(default=False)` y la constante `MAX_FOTOS_ACTA = 3`.
- Create: `backend/mantenimiento/acta.py`, `templates/mantenimiento/acta_pdf.html` y `backend/mantenimiento/views/actas.py` (`acta_pdf`)
- Modify:
  - `views/ordenes.py` (`toggle_foto_acta`);
  - `urls.py`;
  - `detalle_orden.html`: "Descargar acta" si la orden está cerrada y es de formato 2; "PDF (formato anterior)" con `orden_pdf` si es de formato 1; en cada foto, un interruptor "En el acta".
- Modify: `.github/workflows/ci.yml`. En el job `test`, antes de instalar dependencias: `sudo apt-get update && sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core`. Después de las pruebas, con `if: always()`, subir el artifact `actas-muestra` desde `backend/acta_muestras/*.pdf` (`actions/upload-artifact@v4`). Al job le agrega `env: ACTA_MUESTRAS_DIR: acta_muestras`.
- Test: `backend/mantenimiento/test_acta.py`

**Interfaces:**
- Consumes: `datos_acta` (Tarea 6) y `inventario.views.qr._qr_data_uri`.
- Produces (en `acta.py`):
  - `url_hoja_de_vida(request, activo) -> str`: usa `settings.QR_BASE_URL` si existe; si no, `request.build_absolute_uri`. Apunta a `mantenimiento:hoja_de_vida`.
  - `fotos_acta(orden) -> list[FotoMantenimiento]`: las marcadas `en_acta`, ordenadas por `fecha_creacion`. Si no hay marcadas, las 3 primeras. Nunca más de 3.
  - `columnas_checklist(items) -> tuple[list[dict], list[dict]]`: grupos `{"seccion": str, "items": list[ChecklistItem]}` en el orden de los ítems. Cada grupo pesa `len(items) + 1`. Se agregan a la izquierda mientras el peso acumulado de la izquierda sea menor que la mitad del total; el resto va a la derecha, sin partir grupos.
  - `observaciones_acta(orden) -> list[str]`: primero `f"{item.descripcion} (falla): {item.observacion}"` por cada falla, en orden, y después `orden.observaciones` si no está vacía.
  - `resumen_checklist(items) -> dict` con `total`, `bien`, `falla` y `na`.
  - `contexto_acta(orden, request, escala: int = 0) -> dict` con las claves:
    - `orden`, `datos` (`= orden.datos_acta`), `config` (`ConfiguracionSistema.get_config()`), `logo_path` (`services.LOGO_PATH`);
    - `qr` (data URI de `url_hoja_de_vida`), `numero` (`f"{orden.pk:04d}"`), `es_correctivo`;
    - `columnas` y `resumen`, que vienen de los `checklist_items`;
    - `fotos`: lista de `{"path": foto.foto.path, "descripcion": …}`;
    - `repuestos`: lista de cadenas `f"{nombre} × {cantidad}"`, sin costos;
    - `observaciones` (de `observaciones_acta`) y `escala`.
  - `renderizar_acta(orden, request) -> tuple[bytes, int]`: prueba `escala` 0, 1, 2 y 3. Usa `weasyprint.HTML(string=…, base_url=str(settings.BASE_DIR)).render()` y devuelve `(documento.write_pdf(), escala)` con la primera que dé `len(documento.pages) == 1`, o con la escala 3 si ninguna lo logra.
- URLs: `mantenimiento:acta_pdf` → `ordenes/<int:pk>/acta/` y `mantenimiento:toggle_foto_acta` → `fotos/<int:pk>/acta/` (POST). Si ya hay 3 fotos marcadas y se intenta marcar otra: `"Solo caben 3 fotos en el acta."`.
- La vista `acta_pdf` solo responde para órdenes `cerrada` de formato 2. Si no, redirige al detalle con un mensaje. La respuesta es `inline`, con `filename="acta_mantenimiento_{pk:04d}_{serial}.pdf"`.

Plantilla `acta_pdf.html`. Copia el boceto `acta-una-hoja.html` con estas reglas:
- `@page { size: letter; margin: 10mm 12mm; }` y `font-family: "DejaVu Sans", sans-serif`. Las secciones se maquetan con `<table>`, no con flex.
- `<body class="escala-{{ escala }}">` define el tamaño de letra y el alto de las fotos: escala 0 → 8.5pt y 34mm; 1 → 8pt y 30mm; 2 → 7.4pt y 26mm; 3 → 6.8pt y 22mm.
- Secciones en el orden de la §B7 del spec:
  - encabezado con logo, título, `Código: {{ config.acta_mant_codigo|default:"—" }}`, `Versión: …` y `Página 1 de 1`;
  - "1. DATOS DEL MANTENIMIENTO Y DEL EQUIPO": `Acta N° {{ numero }}`, la fecha de cierre, el tipo, los `campos` en 3 pares por fila, Garantía, Próximo y el QR;
  - "2. RESPONSABLE DEL EQUIPO": o `No asignado`;
  - "3. CHECKLIST · {{ resumen.total }} puntos · {{ resumen.bien }} bien · {{ resumen.falla }} con falla": dos columnas `#`, Punto revisado y Resultado (`BIEN` / `FALLA` / `N/A`). En un correctivo, esta sección es "3. DIAGNÓSTICO Y SOLUCIÓN";
  - "4. EVIDENCIA FOTOGRÁFICA": solo si hay fotos, con `file://{{ foto.path }}`;
  - "5. REPUESTOS Y ESTADO FINAL": los repuestos unidos con coma, o `Ninguno`, y el estado final con su etiqueta en color;
  - "6. OBSERVACIONES": las líneas de `observaciones_acta`;
  - firmas, Técnico y Usuario (`No asignado` si no hay responsable);
  - pie `SysAdmin · {código} v{versión} · Acta de mantenimiento N° {numero} · dd/mm/aaaa · Página 1 de 1`.

- [ ] **Step 1: Escribir las pruebas que fallan** (`test_acta.py`)

```python
class FakeDocumento:
    pages = [object()]
    def write_pdf(self):
        return b"%PDF-1.4 acta-fake"

class FakeHTML:
    def __init__(self, *a, **kw):
        pass
    def render(self):
        return FakeDocumento()

FAKE_WEASY = type("M", (), {"HTML": FakeHTML})()


class ArmadoActaTests(TestCase):
    def test_columnas_por_seccion(self): ...       # orden de portátil cerrada → izquierda ["Hardware","Limpieza"], derecha ["Mantenimiento lógico"]
    def test_observaciones_primero_las_fallas(self): ...  # ["Bisagras (falla): Floja", "Revisar en 6 meses"]
    def test_fotos_maximo_3_y_prioriza_marcadas(self): ...
    def test_resumen(self): ...                     # {"total": 12, "bien": 11, "falla": 1, "na": 0}
    @override_settings(QR_BASE_URL="https://sysadmin.local:6060")
    def test_url_hoja_de_vida_usa_qr_base_url(self): ...  # empieza por "https://sysadmin.local:6060/mantenimiento/hoja-de-vida/"

    def test_html_tiene_los_datos_y_no_tiene_columna_de_observacion(self):
        ...  # render_to_string("mantenimiento/acta_pdf.html", contexto_acta(orden, request)) contiene:
             # "ACTA DE MANTENIMIENTO DE EQUIPOS DE CÓMPUTO", "Código: FT-TEST", "Página 1 de 1",
             # "Marta López Gómez", "FALLA", "Bisagras (falla):"; y NO contiene ">Observación<"

    def test_no_asignado_en_responsable_y_firma(self): ...  # contiene "No asignado" 2 veces
    def test_correctivo_muestra_diagnostico_y_solucion(self): ...  # contiene "DIAGNÓSTICO Y SOLUCIÓN"; no "CHECKLIST"


class VistaActaTests(TestCase):
    def test_solo_cerradas_de_formato_actual(self): ...  # abierta → redirect; formato 1 → redirect; cerrada v2 → 200 application/pdf (FAKE_WEASY)
    def test_toggle_foto_acta_maximo_3(self): ...       # 4.ª → mensaje "Solo caben 3 fotos en el acta."


def _weasyprint_real():
    try:
        import weasyprint  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


@skipUnless(_weasyprint_real(), "WeasyPrint real no disponible (Windows sin GTK)")
class ActaUnaHojaTests(TestCase):
    def test_contenido_tipico_sale_en_escala_0(self):
        ...  # 12 puntos (2 fallas de 60 caracteres), 3 fotos PNG de 1600x1200, 1 repuesto, observaciones de 200
             # → renderizar_acta(...)[1] == 0; guarda el PDF en ACTA_MUESTRAS_DIR/acta_tipica.pdf si la variable existe

    def test_contenido_maximo_cabe_en_una_hoja(self):
        ...  # 12 fallas de 150, observaciones de 600, 3 fotos, 5 repuestos de 150 caracteres
             # → weasyprint.HTML(string=render_to_string(..., contexto_acta(orden, req, escala=e))).render() tiene 1 página
             #   con la escala devuelta; guarda ACTA_MUESTRAS_DIR/acta_maxima.pdf
```

Las fotos de prueba se generan con Pillow dentro de un `MEDIA_ROOT` temporal (`override_settings` + `tempfile.TemporaryDirectory`).

- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr y ver que pasan**

Run: `... manage.py test mantenimiento administracion --noinput` → `OK`. En Windows, `ActaUnaHojaTests` sale como `skipped`.

- [ ] **Step 5: Commit** (solo con autorización): `"mantenimiento: acta PDF de una hoja carta con QR, fotos y firmas"`.

---

### Task 8: Subir el acta firmada y avisos de actas sin firmar

**Files:**
- Modify: `backend/mantenimiento/forms.py` (`SubirActaFirmadaForm`), `views/actas.py` (`subir_acta_firmada`) y `urls.py`
- Create: `templates/mantenimiento/subir_acta.html`
- Modify: `backend/core/views.py`, agregando `("mantenimiento/actas/", "mantenimiento")` a `MEDIA_PERMISOS`
- Modify: `backend/notificaciones/services.py`, que agrega `_detectar_actas_mantenimiento(user)` y la llama desde `generar_mantenimiento`
- Modify: `detalle_orden.html`: botón "Subir acta firmada"; enlace "Ver acta firmada"; etiqueta ámbar "De una versión anterior" si `acta_firmada_desactualizada`.
- Test: `backend/mantenimiento/test_acta_firmada.py` y `backend/notificaciones/tests.py`

**Interfaces:**
- Produces:
  - `mantenimiento:subir_acta_firmada` → `ordenes/<int:pk>/acta/subir/`, solo para órdenes cerradas de formato 2. Al guardar, deja `acta_firmada_desactualizada=False`.
  - `SubirActaFirmadaForm`: un campo `archivo`, con `EXTENSIONES_ACTA = {".pdf", ".jpg", ".jpeg", ".png"}` y `LIMITE_ACTA_BYTES = 10 * 1024 * 1024`. Errores:
    - `"Sube un PDF, JPG o PNG."`
    - `"El archivo pasa de 10 MB."`
  - `_detectar_actas_mantenimiento(user)`: por cada orden `cerrada` de formato 2 sin `acta_firmada`, o con `acta_firmada_desactualizada=True`, ejecuta `_crear(user, "mantenimiento", f"Acta de mantenimiento sin firmar · N° {pk:04d}", f"El acta del equipo {serial} aún no tiene la firma escaneada.", link=detalle_orden, objetokey=f"acta_mant:{pk}")`.

- [ ] **Step 1: Escribir las pruebas que fallan**: `test_subir_pdf_guarda_y_quita_desactualizada`, `test_rechaza_extension`, `test_rechaza_mayor_a_10mb` (con `patch("mantenimiento.forms.LIMITE_ACTA_BYTES", 10)`), `test_solo_ordenes_cerradas`, `test_archivo_se_sirve_con_permiso_de_mantenimiento` (un `MEDIA_ROOT` temporal; un GET a la URL del archivo como técnico da 200) y, en notificaciones, `test_aviso_acta_mantenimiento_sin_firmar`, `test_sin_aviso_si_ya_tiene_firmada` y `test_aviso_si_esta_desactualizada`.
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr y ver que pasan**

Run: `... manage.py test mantenimiento notificaciones core --noinput` → `OK`.

- [ ] **Step 5: Commit** (solo con autorización): `"mantenimiento: subir acta firmada y avisar las que faltan"`.

---

### Task 9: Editor de checklists

**Files:**
- Modify: `backend/mantenimiento/forms.py`:
  - `PlantillaChecklistForm` (`tipo_dispositivo` con las opciones de `_opciones_categorias()`, y `frecuencia_meses`);
  - `PuntoPlantillaFormSet = inlineformset_factory(PlantillaChecklist, PuntoPlantilla, fields=["seccion", "descripcion", "posicion", "aplica_en_garantia", "activo"], extra=3, can_delete=True)`.
- Create: `backend/mantenimiento/views/plantillas.py` (`lista_plantillas`, `crear_plantilla` y `editar_plantilla`), y las plantillas `templates/mantenimiento/plantillas.html` y `plantilla_form.html`. El campo sección lleva un `<datalist>` con `SECCIONES_SUGERIDAS`.
- Modify: `urls.py`; `inicio.html` (botón "Checklists"); `core/tests.py` (`RUTAS` + `"mantenimiento:lista_plantillas"` y `"mantenimiento:crear_plantilla"`)
- Test: `backend/mantenimiento/test_checklists.py` (clase nueva `EditorChecklistsTests`)

**Interfaces:**
- Produces:
  - `mantenimiento:lista_plantillas` → `checklists/`;
  - `mantenimiento:crear_plantilla` → `checklists/nueva/`;
  - `mantenimiento:editar_plantilla` → `checklists/<int:pk>/`.
  - Todo escribe con permiso `escritura`.

- [ ] **Step 1: Escribir las pruebas que fallan**:
  - `test_lista_muestra_los_dos_checklists`;
  - `test_editar_cambia_texto_y_frecuencia`;
  - `test_quitar_punto`;
  - `test_editar_no_toca_ordenes_existentes`;
  - `test_crear_para_otro_tipo_lo_vuelve_programable`: crea uno para "Diadema" y comprueba que `activos_programables()` incluye un activo Diadema;
  - `test_tipo_repetido_no_se_permite`;
  - `test_requiere_escritura`.
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr y ver que pasan**

Run: `... manage.py test mantenimiento core.tests.SmokeVistasTests --noinput` → `OK`.

- [ ] **Step 5: Commit** (solo con autorización): `"mantenimiento: editor de checklists por tipo"`.

---

### Task 10: Correctivos con el formulario nuevo

**Files:**
- Modify: `backend/mantenimiento/forms.py`. Agrega `OrdenForm` con los campos `activo`, `prioridad`, `fecha_apertura`, `descripcion`, `diagnostico`, `acciones` (label "Solución / acciones realizadas"), `costo_estimado`, `costo_real` y `software_snapshot_text`. No lleva `tecnico_asignado`. `diagnostico` y `acciones` van con `max_length=600` en el form. Si `instance.tipo == "preventivo"`, el `__init__` quita `activo`, `descripcion`, `diagnostico` y `acciones`.
- Modify: `views/ordenes.py`. `crear_orden` y `editar_orden` usan `OrdenForm`; `crear_orden` fuerza `tipo="correctivo"`, `estado="abierta"` y `formato=2`, y conserva el formset de fotos y el snapshot automático de OCS. El viejo `OrdenMantenimientoForm` queda sin uso y se borra en la Tarea 11.
- Create: `templates/mantenimiento/form_correctivo.html`, sin plan, partes ni casillas de acciones.
- Modify: `detalle_orden.html`. En formato 2 correctivo muestra "Diagnóstico" y "Solución / acciones realizadas". En formato 1 muestra las secciones viejas (acciones, estado de partes y checklist viejo) en solo lectura.
- Test: `backend/mantenimiento/test_correctivos.py`

- [ ] **Step 1: Escribir las pruebas que fallan**:
  - `test_crear_correctivo_formato_actual_sin_checklist`;
  - `test_formulario_no_tiene_campos_viejos`: ningún campo que empiece por `accion_` o `parte_`, ni `plan`;
  - `test_editar_preventivo_no_cambia_el_equipo`;
  - `test_orden_vieja_muestra_estado_de_partes`: una orden de formato 1 con `estado_partes={"pantalla": "mal"}` y activo portátil muestra en su detalle "Pantalla" y "Mal estado";
  - `test_diagnostico_maximo_600`.
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr y ver que pasan**

Run: `... manage.py test mantenimiento soporte --noinput` → `OK`.

- [ ] **Step 5: Commit** (solo con autorización): `"mantenimiento: correctivos con formulario nuevo; órdenes viejas en solo lectura"`.

---

### Task 11: Retirar los planes y conectar la programación

**Files:**
- Modify: `backend/mantenimiento/models.py`, con su migración 0015. Borra `PlanMantenimiento`, `ESTADOS_PLAN` y `CRITICIDADES`; `OrdenMantenimiento.plan`; `ChecklistItem.plan` y `ChecklistItem.completado`; y la propiedad `checklist_items_completados`.
- Delete:
  - `views/planes.py` y `views/legado.py`;
  - las plantillas `lista_planes.html`, `detalle_plan.html`, `form_plan.html`, `partials/tabla_planes.html`, `partials/checklist_orden.html`, `partials/estado_partes.html` y `form_orden.html`;
  - en `forms.py`: `PlanMantenimientoForm`, `ChecklistItemForm`, `OrdenMantenimientoForm`, `_partes_por_activo` y `ESTADO_PARTE_CHOICES`. Se conservan `_opciones_categorias` y `constants.PARTES_POR_TIPO`, que se usa para mostrar las órdenes viejas.
- Modify:
  - `urls.py`: sin rutas de planes, `toggle_checklist`, `estado_partes_partial` ni `crear_item_checklist`;
  - `views/__init__.py` y `admin.py`;
  - `views/reportes.py::calendario_eventos`: deja las órdenes como hoy, quita los planes y agrega un evento por cada `ProgramacionMantenimiento` con fecha (`title=f"Programado · {serial}"`, `start` igual a la fecha, `url` a `hoja_de_vida` y `color="#0156a6"`).
- Modify: `backend/notificaciones/services.py`. Borra `_detectar_mantenimiento` y agrega `_detectar_programacion(user, hoy=None)`, que recorre `tablero(hoy)`:
  - por cada situación `le_toca`, ejecuta `_crear(user, "mantenimiento", f"Le toca mantenimiento · {serial}", f"A {tipo} {marca} {modelo} le toca mantenimiento desde el {fecha:%d/%m/%Y}.", link=reverse("mantenimiento:inicio"), objetokey=f"mant:toca:{pk}:{le_toca_desde.isoformat()}")`;
  - si `fecha_programada == hoy + 1 día`, ejecuta `_crear(..., f"Mañana: mantenimiento de {serial}", …, objetokey=f"mant:prog:{pk}:{fecha.isoformat()}")`.

  `generar_mantenimiento` pasa a llamar `_detectar_programacion` y `_detectar_actas_mantenimiento`.
- Modify: `backend/core/views.py` y `core/templates/core/dashboard.html`. La tarjeta "Ordenes atrasadas" pasa a ser "Les toca mantenimiento", con el valor `tablero()["conteos"]["le_toca"]`, ícono `bi-tools`, color warning y sin la palabra "ALERTA".
- Modify: `backend/reports/views.py::mantenimiento_excel`:
  - `select_related("activo", "tecnico")`;
  - encabezados `["Fecha apertura", "Fecha cierre", "Tipo", "En garantía", "Estado", "Estado final", "Prioridad", "Activo", "Serial", "Técnico", "Costo estimado", "Costo real"]`;
  - "En garantía" vale `Sí` o `No`;
  - "Técnico" es `orden.tecnico.get_full_name()` o, si no hay, `orden.tecnico_asignado`;
  - columnas de dinero `{11, 12}`.
- Modify: pruebas que usan planes:
  - `mantenimiento/tests.py`: borra el ayudante `_plan` y las clases `Planes*`, `ChecklistTests`, `ChecklistEditableTests` y `OrdenAccionesYPartesTests`; actualiza `CalendarioTests` y `CommandNotificacionesMantenimientoTests`;
  - `notificaciones/tests.py`: actualiza `DetectarMantenimientoTests` y `GenerarNotificacionesMantenimientoCommandTests`;
  - `core/tests.py`: saca de `RUTAS` `"mantenimiento:lista_planes"` y `"mantenimiento:crear_plan"`.
- Test: `backend/mantenimiento/test_retiro_planes.py`, `notificaciones/tests.py`, `core/tests.py` y `reports/tests.py`

- [ ] **Step 1: Escribir las pruebas que fallan**:
  - `test_orden_formato_anterior_sigue_visible`: crea una orden correctiva de formato 1, cerrada y con `estado_partes`. Su detalle, `hoja_de_vida`, `hoja_de_vida_pdf` (con weasyprint simulado), `lista_ordenes` y `reports:mantenimiento_excel` deben responder 200;
  - `test_aviso_le_toca_una_vez_por_ciclo`;
  - `test_aviso_programado_manana`;
  - `test_sin_aviso_en_garantia_ni_al_dia`;
  - `test_comando_genera_avisos_de_programacion`;
  - `test_dashboard_muestra_equipos_que_les_toca`;
  - `test_eventos_incluyen_ordenes_y_programados`;
  - `test_excel_mantenimiento_columnas_nuevas`: la fila del encabezado es igual a la lista de arriba;
  - `test_ya_no_existen_rutas_de_planes`: `reverse("mantenimiento:lista_planes")` lanza `NoReverseMatch`.
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar.** Hacer `makemigrations mantenimiento` para la 0015 y revisar que solo contenga los `RemoveField` y el `DeleteModel`.
- [ ] **Step 4: Correr la suite completa**

Run: `... manage.py test --noinput` → `OK`; `makemigrations --check --dry-run` → `No changes detected`.

- [ ] **Step 5: Commit** (solo con autorización): `"mantenimiento: retirar planes por categoría; avisos, calendario, dashboard y Excel con la programación"`.

---

### Task 12: Hoja de vida y reportes con el formato nuevo

**Files:**
- Modify:
  - `backend/mantenimiento/views/reportes.py::hoja_de_vida` y `services.py::hoja_de_vida_pdf_bytes`: a cada orden de formato 2 se le agrega `resumen_checklist(...)`, las fallas (`observaciones_acta` filtradas a las de falla), `estado_final` y los enlaces al acta y al acta firmada;
  - `templates/mantenimiento/hoja_de_vida.html`, `hoja_de_vida_pdf.html` y `reporte_mantenimientos_pdf.html`: sin columna de plan y con "Estado final";
  - `partials/tabla_ordenes.html`: la columna "Plan" pasa a "Técnico".
- Test: `backend/mantenimiento/test_hoja_de_vida_v2.py`

- [ ] **Step 1: Escribir las pruebas que fallan**:
  - `test_hoja_de_vida_muestra_resumen_fallas_y_acta`: una orden cerrada con 1 falla muestra "11 bien", "1 con falla", el texto de la falla y la URL de `acta_pdf`;
  - `test_hoja_de_vida_pdf_incluye_checklist`: `render_to_string` del template del PDF contiene "con falla";
  - `test_historial_sin_columna_plan`: `lista_ordenes` no contiene ">Plan<".
- [ ] **Step 2: Correr y ver que fallan.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Correr y ver que pasan**

Run: `... manage.py test mantenimiento --noinput` → `OK`.

- [ ] **Step 5: Commit** (solo con autorización): `"mantenimiento: hoja de vida y reportes con checklist, estado final y actas"`.

---

### Task 13: Verificación final, revisión del acta real y documentación

**Files:**
- Modify: `README.md` (módulo Mantenimiento y changelog), `AGENTS.md` (reglas nuevas y número de tests) y `SYSADMIN_HANDOFF.md` (sección v1.13)

- [ ] **Step 1: Correr la suite, el lint y las comprobaciones**

Run (desde `backend/`):
- `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test --noinput` → `OK`
- `../.venv/Scripts/ruff.exe check .` → `All checks passed!`
- `POSTGRES_DB= ../.venv/Scripts/python.exe manage.py makemigrations --check --dry-run` → `No changes detected`
- `POSTGRES_DB= ../.venv/Scripts/python.exe manage.py check` → `System check identified no issues`

- [ ] **Step 2: CI y actas de muestra** (requiere que el usuario autorice el push de la rama)

- Hacer push de la rama y esperar el CI: `gh run watch`. Esperado: lint, test, test-postgres y audit en success, con `ActaUnaHojaTests` **ejecutadas, no skipped**. Se comprueba con `gh run view --log | grep ActaUnaHoja`.
- Descargar las muestras con `gh run download <id> -n actas-muestra -D <scratchpad>/actas` y abrir `acta_tipica.pdf` y `acta_maxima.pdf` con la herramienta Read.
- Comprobar visualmente que cada una ocupa una sola hoja carta y que se parecen al boceto aprobado: encabezado con código, QR, checklist en dos columnas, fotos, cuadro de observaciones antes de las firmas y "No asignado" donde corresponde.

- [ ] **Step 3: Recorrido manual local** (`runserver` con SQLite)

1. Crear un portátil sin garantía y uno en garantía, y comprobar sus pestañas.
2. Programar una fecha y cambiarla.
3. Iniciar, marcar una falla sin observación (debe salir el error), completarla y cerrar. Con una cuenta sin nombre, debe pedir nombre y cargo.
4. Reabrir.
5. Editar un checklist.
6. Crear un correctivo.
7. Abrir la orden vieja en formato anterior.

En Windows el PDF no se genera, así que la descarga del acta se revisa con las muestras de CI.

- [ ] **Step 4: Documentar**

- `README.md`: reescribir la sección del módulo Mantenimiento (pantalla por equipo, checklists, programación, acta y acta firmada) y agregar la entrada de changelog v1.13.
- `AGENTS.md`: agregar las reglas nuevas:
  - el acta siempre se genera desde `datos_acta`;
  - "Sin rojos" en la programación;
  - el acta usa la fuente DejaVu Sans y una sola hoja;
  - y actualizar el número de tests.
- `SYSADMIN_HANDOFF.md`: describir los modelos nuevos, las migraciones 0009 a 0015, accounts 0003 y administracion 0004, y los pasos de despliegue (backup y migrate).

- [ ] **Step 5: Commit** (solo con autorización): `"docs: mantenimiento v2"`.

El despliegue a producción no es parte de este plan. Se hace con `GUIA_DEPLOY_PASO_A_PASO.md`, backup `pg_dump -Fc` previo y la aprobación del usuario, y después se verifica en producción que la orden vieja y las 2 plantillas estén bien.
