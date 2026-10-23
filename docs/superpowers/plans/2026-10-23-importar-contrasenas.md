# Importación masiva de contraseñas desde Excel — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que dentro de cada bóveda se pueda descargar una plantilla Excel, pegar las contraseñas, subirla, revisar una vista previa y confirmar la importación, sin que ninguna clave quede en texto plano en el servidor.

**Architecture:** La lectura y la validación del Excel viven en un módulo nuevo, `passwords/importacion.py`, hecho de funciones puras que reciben el archivo y la bóveda. Las vistas siguen el patrón de importar activos (`inventario/views/excel.py`): subir, vista previa guardada en la sesión y confirmar. Cada clave se cifra con `build_fernet()` en cuanto se lee, así que en la sesión y en la vista previa solo existe el texto cifrado.

**Tech Stack:** Django 5.2, openpyxl 3.1.5, cryptography (Fernet vía `passwords/crypto.py`) y Bootstrap 5.

**Spec:** `docs/superpowers/specs/2026-10-23-mantenimiento-y-contrasenas-design.md` (Parte A)

## Global Constraints

- Comando de pruebas (Git Bash, desde `backend/`): `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test <etiqueta> --noinput`. `POSTGRES_DB=` vacío obliga a usar SQLite local; sin eso intenta conectarse al host `db`.
- Lint (desde `backend/`): `../.venv/Scripts/ruff.exe check .`
- Las pruebas usan datos inventados. El repo es público: nada de claves reales en código, pruebas o docs.
- Los commits no llevan `Co-Authored-By` ni menciones a Claude o Anthropic. No hacer commit ni push sin autorización explícita del usuario (AGENTS.md). Trabajar en la rama `feat/importar-contrasenas`.
- Interfaz en español.
- Permiso para importar y para descargar la plantilla: `@requiere_permiso("passwords", "escritura")`. Hoy solo lo tiene el rol `superadmin`.
- Límites: solo `.xlsx`, máximo **1.000 filas con datos** y **5 MB**.
- Encabezados exactos de la plantilla: `Título`, `Usuario`, `Contraseña`, `URL`, `Notas`, `Estado`, `Fecha de expiración`.
- Un duplicado es el mismo título y el mismo usuario (sin distinguir mayúsculas y sin espacios al inicio ni al final) **dentro de la misma bóveda**. Los duplicados nunca se sobrescriben.
- Las claves no aparecen nunca en la sesión, en el HTML, en `AccesoLog` ni en los logs.

## Review Focus

1. **Una clave numérica o con forma de fecha pegada sin la plantilla.** Excel guarda `123456` como `123456.0` y `1/2/24` como fecha. Lo esperado es que `123456` se guarde tal cual, sin `.0`, y que la fecha salga como error explicado, nunca como `2024-02-01 00:00:00`. Lo cubre `test_clave_numerica_no_pierde_formato` / `test_clave_convertida_en_fecha_es_error` (Tarea 1).
2. **Confirmar en otra bóveda o dos veces.** La vista previa de la bóveda A no puede crear nada en la B, y al recargar la página de confirmación no se duplica nada. Lo cubren `test_confirmar_es_por_boveda` y `test_confirmar_dos_veces_no_duplica` (Tarea 3).
3. **La misma credencial dos veces en el archivo.** La segunda fila sale como "Repetida en el archivo" y solo se crea una. Lo cubre `test_repetida_dentro_del_archivo` (Tarea 1).
4. **Una URL que no es URL** ("intranet", una IP sin esquema o más de 200 caracteres). No debe tumbar la fila: va a Notas o se le antepone `https://`. Lo cubre `test_url_invalida_va_a_notas` (Tarea 1).
5. **Claves con espacios.** Una clave con espacios al inicio o al final se conserva exacta. Lo cubre `test_contrasena_conserva_espacios` (Tarea 1).

---

### Task 1: Leer y validar el Excel (`passwords/importacion.py`)

**Files:**
- Create: `backend/passwords/importacion.py`
- Test: `backend/passwords/tests.py` (clase nueva `ImportacionLecturaTests`)

**Interfaces:**
- Consumes: `passwords.crypto.build_fernet()`, `passwords.models.Credencial`, `Vault`, `ESTADOS_CREDENCIAL`.
- Produces:
  - `MAX_FILAS: int = 1000`
  - `MAX_BYTES: int = 5 * 1024 * 1024`
  - `class ArchivoInvalido(Exception)`: su `str()` es el mensaje para el usuario.
  - `leer_credenciales(archivo, vault: Vault) -> tuple[list[dict], list[str]]`. Devuelve `(filas, advertencias)`. Cada fila es un `dict` serializable a JSON con estas claves:
    - `fila` (int, número de fila en Excel)
    - `titulo`, `usuario`, `url`, `notas` (str)
    - `estado` (`"activa"`, `"expirada"` o `"revocada"`)
    - `fecha_expiracion` (str ISO o `None`)
    - `secreto_cifrado` (str; vacío si la fila no es `"nueva"`)
    - `resultado` (`"nueva"`, `"ya_existe"`, `"repetida"` o `"error"`)
    - `detalle` (str con el motivo, vacío si es nueva)
  - `resumen(filas: list[dict]) -> dict` con las claves `nuevas`, `ya_existen` (suma `ya_existe` y `repetida`), `errores` y `total`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al principio de `backend/passwords/tests.py`:

```python
from datetime import date
from io import BytesIO
from unittest.mock import patch

from openpyxl import Workbook

from passwords.crypto import build_fernet

ENCABEZADOS = ("Título", "Usuario", "Contraseña", "URL", "Notas", "Estado", "Fecha de expiración")


def _xlsx(filas, encabezados=ENCABEZADOS, nombre="claves.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.append(list(encabezados))
    for fila in filas:
        ws.append(list(fila))
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    buffer.name = nombre
    return buffer


def _descifrar(token):
    return build_fernet().decrypt(token.encode()).decode()
```

Clase nueva:

```python
class ImportacionLecturaTests(TestCase):
    def setUp(self):
        self.vault = _vault()

    def _leer(self, filas, **kw):
        from passwords.importacion import leer_credenciales
        return leer_credenciales(_xlsx(filas, **kw), self.vault)

    def test_fila_valida_queda_nueva_y_cifrada(self):
        filas, avisos = self._leer([("Router", "admin", "S3creta!", "192.168.1.1", "", "", "")])
        self.assertEqual(avisos, [])
        f = filas[0]
        self.assertEqual((f["fila"], f["resultado"], f["estado"]), (2, "nueva", "activa"))
        self.assertEqual(f["url"], "https://192.168.1.1")
        self.assertNotIn("S3creta!", f["secreto_cifrado"])
        self.assertEqual(_descifrar(f["secreto_cifrado"]), "S3creta!")

    def test_falta_titulo_o_contrasena_es_error(self):
        filas, _ = self._leer([("", "u", "x"), ("T", "u", "")])
        self.assertEqual([f["resultado"] for f in filas], ["error", "error"])
        self.assertEqual(filas[0]["detalle"], "Falta el título")
        self.assertEqual(filas[1]["detalle"], "Falta la contraseña")
        self.assertEqual(filas[1]["secreto_cifrado"], "")

    def test_ya_existe_en_la_boveda_por_titulo_y_usuario_sin_mayusculas(self):
        Credencial.objects.create(vault=self.vault, titulo="Router", usuario="Admin")
        filas, _ = self._leer([(" router ", "admin", "x")])
        self.assertEqual(filas[0]["resultado"], "ya_existe")
        self.assertEqual(filas[0]["secreto_cifrado"], "")
        from passwords.importacion import leer_credenciales
        otra, _ = leer_credenciales(_xlsx([(" router ", "admin", "x")]), _vault("Otra"))
        self.assertEqual(otra[0]["resultado"], "nueva")

    def test_repetida_dentro_del_archivo(self):
        filas, _ = self._leer([("Router", "admin", "a"), ("ROUTER", "Admin ", "b")])
        self.assertEqual([f["resultado"] for f in filas], ["nueva", "repetida"])
        self.assertEqual(filas[1]["detalle"], "Repetida en el archivo")

    def test_encabezados_alternativos(self):
        filas, avisos = self._leer([("NAS", "root", "x", "nas.local")], encabezados=("Nombre", "User", "Clave", "Sitio"))
        self.assertEqual(avisos, [])
        self.assertEqual((filas[0]["titulo"], filas[0]["usuario"], filas[0]["resultado"]), ("NAS", "root", "nueva"))

    def test_clave_numerica_no_pierde_formato(self):
        filas, _ = self._leer([("A", "u1", 123456), ("B", "u2", 123456.0)])
        self.assertEqual([_descifrar(f["secreto_cifrado"]) for f in filas], ["123456", "123456"])

    def test_clave_convertida_en_fecha_es_error(self):
        filas, _ = self._leer([("A", "u", date(2024, 2, 1))])
        self.assertEqual(filas[0]["resultado"], "error")
        self.assertIn("fecha", filas[0]["detalle"])

    def test_estado_y_fecha(self):
        filas, _ = self._leer([
            ("A", "u1", "x", "", "", "Revocada", "31/12/2027"),
            ("B", "u2", "x", "", "", "Bloqueada", ""),
            ("C", "u3", "x", "", "", "", "31-31-2027"),
            ("D", "u4", "x", "", "", "expirada", date(2027, 1, 15)),
        ])
        self.assertEqual((filas[0]["estado"], filas[0]["fecha_expiracion"]), ("revocada", "2027-12-31"))
        self.assertEqual(filas[1]["resultado"], "error")
        self.assertIn("Estado no válido", filas[1]["detalle"])
        self.assertEqual(filas[2]["resultado"], "error")
        self.assertIn("Fecha de expiración no válida", filas[2]["detalle"])
        self.assertEqual((filas[3]["estado"], filas[3]["fecha_expiracion"]), ("expirada", "2027-01-15"))

    def test_url_invalida_va_a_notas(self):
        filas, _ = self._leer([("A", "u", "x", "intranet de contabilidad", "Nota previa")])
        self.assertEqual(filas[0]["resultado"], "nueva")
        self.assertEqual(filas[0]["url"], "")
        self.assertEqual(filas[0]["notas"], "Nota previa\nSitio: intranet de contabilidad")

    def test_columna_contrasena_faltante_advierte(self):
        filas, avisos = self._leer([("A", "u")], encabezados=("Título", "Usuario"))
        self.assertEqual(avisos, ['No se encontró la columna "Contraseña".'])
        self.assertEqual(filas[0]["resultado"], "error")

    def test_filas_vacias_se_omiten_y_hay_limite(self):
        filas, _ = self._leer([("A", "u", "x"), (None, None, None), ("B", "u", "y")])
        self.assertEqual([f["fila"] for f in filas], [2, 4])
        from passwords.importacion import ArchivoInvalido
        with patch("passwords.importacion.MAX_FILAS", 1):
            with self.assertRaises(ArchivoInvalido):
                self._leer([("A", "u", "x"), ("B", "u", "y")])

    def test_contrasena_conserva_espacios(self):
        filas, _ = self._leer([("A", "u", " a b ")])
        self.assertEqual(_descifrar(filas[0]["secreto_cifrado"]), " a b ")

    def test_titulo_muy_largo_es_error(self):
        filas, _ = self._leer([("T" * 151, "u", "x")])
        self.assertEqual(filas[0]["detalle"], "El título supera 150 caracteres")

    def test_resumen(self):
        from passwords.importacion import resumen
        filas = [{"resultado": r} for r in ("nueva", "nueva", "ya_existe", "repetida", "error")]
        self.assertEqual(resumen(filas), {"nuevas": 2, "ya_existen": 2, "errores": 1, "total": 5})
```

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test passwords.tests.ImportacionLecturaTests --noinput`
Expected: FAIL / ERROR con `ModuleNotFoundError: No module named 'passwords.importacion'`.

- [ ] **Step 3: Implementar `backend/passwords/importacion.py`**

- Leer con `openpyxl.load_workbook(archivo, data_only=True)`, la primera hoja, con los encabezados en la fila 1. **No usar `read_only=True`**: en ese modo openpyxl puede saltarse las filas vacías y la numeración saldría corrida. Iterar con `enumerate(ws.iter_rows(min_row=2, values_only=True), start=2)`.
- Normalizar cada encabezado así: minúsculas, sin tildes (`unicodedata.normalize("NFKD")` y descartar los combinantes), sin `*` y con los espacios colapsados. Luego mapearlo con estos alias:
  - `titulo`: titulo, nombre, servicio, sistema, aplicacion
  - `usuario`: usuario, user, login, cuenta, correo, email
  - `secreto`: contrasena, clave, password, pass
  - `url`: url, sitio, sitio web, enlace, link, direccion, ip
  - `notas`: notas, nota, observaciones, comentarios, descripcion
  - `estado`: estado
  - `fecha_expiracion`: fecha de expiracion, expiracion, vence, vencimiento, fecha de vencimiento
- Si falta la columna de `titulo` o la de `secreto`, agregar a las advertencias exactamente `'No se encontró la columna "Título".'` o `'No se encontró la columna "Contraseña".'`. En ese caso todas las filas quedan en error con detalle `Falta la columna …`.
- Convertir cada celda a texto así:
  - `None` → `""`.
  - `int` → `str(v)`.
  - `float` entero → `str(int(v))`; `float` con decimales → `str(v)`.
  - `datetime` o `date`: en la contraseña, error `"Excel convirtió la contraseña en fecha; usa la plantilla (columnas en Texto)"`; en la fecha de expiración se acepta como fecha.
- A todo menos la contraseña se le aplica `strip()`. Una fila con todas las celdas vacías se omite. Si quedan más de `MAX_FILAS` filas con datos, lanzar `ArchivoInvalido(f"El archivo tiene más de {MAX_FILAS} filas con datos.")`.
- Validar en este orden; el primer error gana:
  1. Título vacío → `"Falta el título"`.
  2. Contraseña vacía (o solo espacios) → `"Falta la contraseña"`.
  3. Título > 150 → `"El título supera 150 caracteres"`.
  4. Usuario > 150 → `"El usuario supera 150 caracteres"`.
  5. Estado: vacío se toma como `activa`; si no es `activa`, `expirada` ni `revocada` (sin tildes ni mayúsculas) → `f"Estado no válido: «{valor}». Usa Activa, Expirada o Revocada"`.
  6. Fecha: acepta `dd/mm/aaaa`, `aaaa-mm-dd` o una celda de fecha; cualquier otra cosa → `f"Fecha de expiración no válida: «{valor}»"`.
- URL:
  - Si no trae `://`, anteponer `https://`.
  - Validar con `django.core.validators.URLValidator`.
  - Si no es válida o pasa de 200 caracteres, la URL queda vacía y se agrega `f"Sitio: {original}"` a las notas, unido con `"\n"` si ya había notas.
- Duplicados:
  - Clave `(titulo.strip().lower(), usuario.strip().lower())`.
  - Si la clave ya existe en `Credencial.objects.filter(vault=vault)`, la fila es `ya_existe`, con detalle `"Ya existe: mismo título y usuario"`.
  - Si la clave ya apareció antes en el archivo, la fila es `repetida`.
- Cifrar con `build_fernet().encrypt(secreto.encode("utf-8")).decode("utf-8")` solo las filas `nueva`.

- [ ] **Step 4: Correr las pruebas y ver que pasan**

Run: `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test passwords.tests.ImportacionLecturaTests --noinput`
Expected: `OK` (14 tests).

- [ ] **Step 5: Commit** (solo con autorización del usuario)

```bash
git add backend/passwords/importacion.py backend/passwords/tests.py
git commit -m "passwords: leer y validar credenciales desde Excel (cifradas al leer)"
```

---

### Task 2: Plantilla descargable

**Files:**
- Modify: `backend/passwords/importacion.py` (agrega `plantilla_workbook`)
- Modify: `backend/passwords/views.py` (agrega la vista `plantilla_importar`)
- Modify: `backend/passwords/urls.py`
- Modify: `backend/core/tests.py` (agrega `"passwords:importar_plantilla"` a `SmokeVistasTests.RUTAS`)
- Test: `backend/passwords/tests.py` (clase nueva `PlantillaImportacionTests`)

**Interfaces:**
- Consumes: `leer_credenciales` (Tarea 1) y `core.utils.guardar_excel`.
- Produces:
  - `plantilla_workbook() -> openpyxl.Workbook`
  - URL `passwords:importar_plantilla` → `importar/plantilla/`, que descarga `plantilla_importar_contrasenas.xlsx`

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
class PlantillaImportacionTests(TestCase):
    def setUp(self):
        self.client.force_login(_user("superadmin"))

    def _descargar(self):
        from openpyxl import load_workbook
        resp = self.client.get(reverse("passwords:importar_plantilla"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("plantilla_importar_contrasenas.xlsx", resp["Content-Disposition"])
        return resp, load_workbook(BytesIO(resp.content))

    def test_hojas_encabezados_y_formato_texto(self):
        _, wb = self._descargar()
        self.assertEqual(wb.sheetnames, ["Plantilla Contraseñas", "Instrucciones"])
        ws = wb["Plantilla Contraseñas"]
        self.assertEqual([c.value for c in ws[1]], list(ENCABEZADOS))
        self.assertEqual(ws["C2"].number_format, "@")
        self.assertEqual(ws["C500"].number_format, "@")

    def test_la_plantilla_se_puede_importar_tal_cual(self):
        from passwords.importacion import leer_credenciales
        resp, _ = self._descargar()
        archivo = BytesIO(resp.content)
        archivo.name = "plantilla.xlsx"
        filas, avisos = leer_credenciales(archivo, _vault())
        self.assertEqual(avisos, [])
        self.assertEqual([f["resultado"] for f in filas], ["nueva", "nueva"])

    def test_admin_con_lectura_no_descarga(self):
        self.client.force_login(_user("admin"))
        resp = self.client.get(reverse("passwords:importar_plantilla"))
        self.assertRedirects(resp, reverse("core:dashboard"))
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test passwords.tests.PlantillaImportacionTests --noinput`
Expected: ERROR `NoReverseMatch: Reverse for 'importar_plantilla' not found`.

- [ ] **Step 3: Implementar**

- `plantilla_workbook()`:
  - Hoja `"Plantilla Contraseñas"` con los 7 encabezados exactos, en fondo `0156A6`, letra blanca en negrita y bordes delgados, igual que `inventario/views/excel.py::descargar_plantilla_activos`.
  - Dos filas de ejemplo:
    - `("Correo Gerencia", "gerencia@empresa.com", "Ejemplo-Clave-1", "https://outlook.office.com", "Cuenta principal", "Activa", "")`
    - `("Router oficina", "admin", "Ejemplo-Clave-2", "http://192.168.1.1", "", "Activa", "31/12/2027")`
  - `number_format = "@"` en A1:G1001.
  - Ancho de 26 en todas las columnas.
  - Hoja `"Instrucciones"`: columnas obligatorias, valores de Estado, formatos de fecha, "duplicado = mismo título y usuario en la bóveda: se omite", el límite de 1.000 filas y "borra el archivo cuando termines".
- Vista `plantilla_importar(request)` con `@requiere_permiso("passwords", "escritura")`: responde el xlsx con `guardar_excel`.
- `urls.py`: `path("importar/plantilla/", views.plantilla_importar, name="importar_plantilla")`.
- `core/tests.py`: agregar `"passwords:importar_plantilla"` a `RUTAS`.

- [ ] **Step 4: Correr y ver que pasan**

Run: `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test passwords.tests.PlantillaImportacionTests core.tests.SmokeVistasTests --noinput`
Expected: `OK`.

- [ ] **Step 5: Commit** (solo con autorización)

```bash
git add backend/passwords backend/core/tests.py
git commit -m "passwords: plantilla Excel para importar contraseñas"
```

---

### Task 3: Subir, vista previa y confirmar (por bóveda)

**Files:**
- Modify: `backend/passwords/views.py` (agrega `credenciales_importar` y `credenciales_importar_confirmar`)
- Modify: `backend/passwords/urls.py`
- Create: `backend/passwords/templates/passwords/importar.html`
- Create: `backend/passwords/templates/passwords/importar_preview.html`
- Modify: `backend/passwords/templates/passwords/credenciales_list.html` (botón "Importar desde Excel")
- Test: `backend/passwords/tests.py` (clase nueva `ImportacionVistasTests`)

**Interfaces:**
- Consumes: `leer_credenciales`, `resumen`, `ArchivoInvalido`, `MAX_BYTES` (Tarea 1), `passwords:importar_plantilla` (Tarea 2) y `_log_action` (`views.py`).
- Produces:
  - URL `passwords:credenciales_importar` → `vaults/<int:vault_id>/credenciales/importar/`, que en GET muestra el formulario y en POST la vista previa.
  - URL `passwords:credenciales_importar_confirmar` → `vaults/<int:vault_id>/credenciales/importar/confirmar/` (solo POST).
  - Clave de sesión `f"importar_credenciales:{vault.pk}"` → `{"archivo": str, "filas": list[dict]}`.
  - `AccesoLog.accion == "importacion_excel"`, con detalle `f"{archivo}: {creadas} creadas, {omitidas} omitidas"`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
import json


class ImportacionVistasTests(TestCase):
    CLAVE = "Clave-Secreta-XYZ"

    def setUp(self):
        self.client.force_login(_user("superadmin"))
        self.vault = _vault()

    def _url(self, nombre, vault=None):
        return reverse(f"passwords:{nombre}", kwargs={"vault_id": (vault or self.vault).pk})

    def _previsualizar(self, filas=None, vault=None, nombre="claves.xlsx"):
        filas = filas or [("Router", "admin", self.CLAVE, "192.168.1.1")]
        return self.client.post(self._url("credenciales_importar", vault), {"archivo": _xlsx(filas, nombre=nombre)})

    def test_preview_no_guarda_nada_ni_muestra_la_clave(self):
        resp = self._previsualizar()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Credencial.objects.count(), 0)
        self.assertNotContains(resp, self.CLAVE)
        self.assertContains(resp, "••••••••")
        self.assertNotIn(self.CLAVE, json.dumps(dict(self.client.session)))

    def test_confirmar_crea_credenciales_cifradas_y_registra_log(self):
        self._previsualizar()
        resp = self.client.post(self._url("credenciales_importar_confirmar"))
        self.assertRedirects(resp, self._url("credenciales_lista"))
        cred = Credencial.objects.get(vault=self.vault)
        self.assertEqual(cred.get_secret(), self.CLAVE)
        self.assertEqual(cred.url, "https://192.168.1.1")
        log = AccesoLog.objects.get(vault=self.vault, accion="importacion_excel")
        self.assertEqual(log.detalle, "claves.xlsx: 1 creadas, 0 omitidas")
        self.assertNotIn(self.CLAVE, log.detalle)

    def test_confirmar_sin_preview_avisa_que_expiro(self):
        resp = self.client.post(self._url("credenciales_importar_confirmar"), follow=True)
        self.assertContains(resp, "La vista previa expiró")
        self.assertEqual(Credencial.objects.count(), 0)

    def test_confirmar_dos_veces_no_duplica(self):
        self._previsualizar()
        self.client.post(self._url("credenciales_importar_confirmar"))
        self.client.post(self._url("credenciales_importar_confirmar"))
        self.assertEqual(Credencial.objects.count(), 1)

    def test_no_sobrescribe_existentes(self):
        vieja = Credencial(vault=self.vault, titulo="Router", usuario="admin")
        vieja.set_secret("vieja")
        vieja.save()
        self._previsualizar()
        self.client.post(self._url("credenciales_importar_confirmar"))
        self.assertEqual(Credencial.objects.count(), 1)
        vieja.refresh_from_db()
        self.assertEqual(vieja.get_secret(), "vieja")

    def test_confirmar_es_por_boveda(self):
        otra = _vault("Otra")
        self._previsualizar()
        resp = self.client.post(self._url("credenciales_importar_confirmar", otra), follow=True)
        self.assertContains(resp, "La vista previa expiró")
        self.assertEqual(Credencial.objects.count(), 0)

    def test_rechaza_archivo_que_no_es_xlsx(self):
        resp = self._previsualizar(nombre="claves.csv")
        self.assertRedirects(resp, self._url("credenciales_importar"))
        self.assertNotIn(f"importar_credenciales:{self.vault.pk}", self.client.session)

    def test_rechaza_archivo_muy_grande(self):
        with patch("passwords.importacion.MAX_BYTES", 10):
            resp = self._previsualizar()
        self.assertRedirects(resp, self._url("credenciales_importar"))
        self.assertNotIn(f"importar_credenciales:{self.vault.pk}", self.client.session)

    def test_admin_con_lectura_no_puede_importar(self):
        self.client.force_login(_user("admin"))
        self.assertRedirects(self.client.get(self._url("credenciales_importar")), reverse("core:dashboard"))

    def test_boton_importar_solo_con_escritura(self):
        url = self._url("credenciales_importar")
        self.assertContains(self.client.get(self._url("credenciales_lista")), url)
        self.client.force_login(_user("admin"))
        self.assertNotContains(self.client.get(self._url("credenciales_lista")), url)
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test passwords.tests.ImportacionVistasTests --noinput`
Expected: ERROR `NoReverseMatch` para `credenciales_importar`.

- [ ] **Step 3: Implementar las vistas, las URLs y las plantillas**

- En `views.py`, importar el módulo con `from . import importacion` y usar `importacion.MAX_BYTES`, `importacion.leer_credenciales`, etc. Así el `patch("passwords.importacion.MAX_BYTES", …)` de las pruebas surte efecto.
- `credenciales_importar(request, vault_id)`, con `@requiere_permiso("passwords", "escritura")`:
  - En GET muestra `passwords/importar.html`.
  - En POST, si falta el archivo, no termina en `.xlsx` (sin distinguir mayúsculas) o pasa de `MAX_BYTES`, muestra `messages.error` y redirige a `credenciales_importar`.
  - Si `leer_credenciales` lanza `ArchivoInvalido`, muestra `messages.error(str(exc))`. Ante cualquier otra excepción, registra `logger.exception` y muestra `"No se pudo leer el archivo. ¿Es un .xlsx válido?"`.
  - Si todo va bien, guarda en la sesión `{"archivo": archivo.name, "filas": filas}`, convierte las advertencias en `messages.warning` y muestra `passwords/importar_preview.html` con `vault`, `filas`, `resumen` y `nombre_archivo`.
- `credenciales_importar_confirmar(request, vault_id)`, con `@requiere_permiso("passwords", "escritura")`:
  - Si no es POST, redirige a `credenciales_importar`.
  - Hace `pop` de la clave de sesión de **esa** bóveda; si no existe, `messages.error("La vista previa expiró. Vuelve a subir el archivo.")`.
  - Por cada fila `nueva`, vuelve a verificar el duplicado contra la BD (con la misma clave en minúsculas y sin espacios). Si sigue libre, crea `Credencial(vault, titulo, usuario, url, notas, estado, fecha_expiracion=date.fromisoformat(...) o None, secreto_encriptado=fila["secreto_cifrado"], creado_por=request.user)`.
  - Registra `_log_action(vault, request.user, "importacion_excel", detalle=...)`.
  - Muestra `messages.success(f"Importación terminada: {creadas} contraseñas creadas, {omitidas} omitidas.")` y `messages.warning("Borra el Excel de tu PC y de la papelera: tiene las contraseñas en texto plano.")`.
  - Redirige a `credenciales_lista`.
- URLs: `path("vaults/<int:vault_id>/credenciales/importar/", ...)` y `path("vaults/<int:vault_id>/credenciales/importar/confirmar/", ...)`.
- `importar.html`: copiar la estructura de `inventario/templates/inventario/importar.html`:
  - Breadcrumb Contraseñas › ‹bóveda› › Importar.
  - Texto con las columnas reconocidas y sus alias, y botón "Descargar plantilla" (`passwords:importar_plantilla`).
  - `<input type="file" name="archivo" accept=".xlsx">` y "Nada se guarda hasta confirmar".
- `importar_preview.html`: copiar la estructura de `inventario/templates/inventario/importar_preview.html`:
  - Tarjetas Nuevas / Ya existen (se omiten) / Con error / Total.
  - Tabla Fila, Título, Usuario, Contraseña, URL y Resultado. La contraseña se muestra como `••••••••` si es nueva y como `—` si no.
  - Etiquetas: `nueva` → "Nueva" (verde); `ya_existe` y `repetida` → el `detalle` (ámbar); `error` → el `detalle` (rojo).
  - Aviso naranja: "Cuando termines, borra el Excel de tu PC (y de la papelera): tiene las contraseñas en texto plano."
  - Botón de confirmar solo si `resumen.nuevas > 0`, con el texto `Importar {{ resumen.nuevas }} contraseñas`.
- `credenciales_list.html`: dentro del bloque de botones, `{% tiene_permiso 'passwords' 'escritura' as puede_escribir %}`. Si lo tiene, mostrar `<a class="btn btn-outline-primary" href="{% url 'passwords:credenciales_importar' vault_id=vault.id %}"><i class="bi bi-file-earmark-arrow-up"></i> Importar desde Excel</a>`.

- [ ] **Step 4: Correr las pruebas de la app**

Run: `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test passwords --noinput`
Expected: `OK`. Son las pruebas que ya había más las 27 nuevas.

- [ ] **Step 5: Commit** (solo con autorización)

```bash
git add backend/passwords
git commit -m "passwords: importar contraseñas desde Excel con vista previa por bóveda"
```

---

### Task 4: Verificación completa y documentación

**Files:**
- Modify: `README.md` (módulo Contraseñas y changelog)
- Modify: `AGENTS.md` (conteo de tests)

- [ ] **Step 1: Correr la suite completa, el lint y el chequeo de migraciones**

Run (desde `backend/`):
- `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test --noinput` → Expected: `OK`.
- `../.venv/Scripts/ruff.exe check .` → Expected: `All checks passed!`
- `POSTGRES_DB= ../.venv/Scripts/python.exe manage.py makemigrations --check --dry-run` → Expected: `No changes detected`.

- [ ] **Step 2: Prueba manual en el navegador**

Levantar `POSTGRES_DB= ../.venv/Scripts/python.exe manage.py runserver` y entrar con un superadmin. Luego:
1. Descargar la plantilla.
2. Pegar 3 filas: una válida, una con la clave `00123` y una repetida.
3. Subirla y comprobar que la vista previa no muestra claves.
4. Confirmar y comprobar que "Ver secreto" muestra `00123` exacto.

- [ ] **Step 3: Documentar**

- `README.md`: en el módulo Contraseñas, agregar "Importación masiva desde Excel por bóveda (plantilla, vista previa, sin sobrescribir)". En el changelog, una entrada con la fecha del despliegue.
- `AGENTS.md`: actualizar el número de tests con el total que reporte el Step 1.

- [ ] **Step 4: Commit** (solo con autorización)

```bash
git add README.md AGENTS.md
git commit -m "docs: importación de contraseñas desde Excel"
```

El despliegue a producción no es parte de este plan: se hace con el procedimiento de `GUIA_DEPLOY_PASO_A_PASO.md` y solo con la aprobación del usuario.
