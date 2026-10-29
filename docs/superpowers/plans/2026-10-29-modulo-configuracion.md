# Módulo de Configuración · Plan de implementación (Fase A)

> **Para quien ejecute esto:** SUB-SKILL OBLIGATORIA: usar
> `superpowers:subagent-driven-development` (recomendada) o
> `superpowers:executing-plans` para implementar tarea por tarea. Los pasos usan
> casillas (`- [ ]`) para llevar la cuenta.

**Meta:** que la configuración de SysAdmin —permisos, módulos activos, correo,
seguridad y retención— se cambie desde la pantalla de Configuración y aplique en el
siguiente request, sin editar código ni reiniciar el contenedor.

**Arquitectura:** la configuración vive en modelos de `administracion` con campos con
tipo (no un almacén clave-valor, no `django-constance`). Un resolvedor único y cacheado
(`accounts.permisos.nivel_permiso`) reemplaza las cuatro lecturas directas del dict
`PERMISOS_POR_ROL`, y de él cuelgan tanto los permisos por rol como el apagado de
módulos. Los tres settings que Django lee al arrancar se vuelven dinámicos sin reiniciar:
la sesión por middleware y los dos de `axes` por callable (`axes` los admite).

**Stack:** Django 5.2.18 · PostgreSQL 15 (SQLite en local) · django-axes 8.3.1 · HTMX ·
Bootstrap 5 vendorizado. **Sin dependencias nuevas.**

**Spec:** `docs/superpowers/specs/2026-10-29-configuracion-y-mesa-de-ayuda-design.md`

## Restricciones globales

- Español en código, interfaz, docstrings y commits. **Commits sin `Co-Authored-By`,
  sin «Generated with» y sin mencionar a Claude ni a Anthropic.**
- Sin dependencias nuevas en `requirements.txt`. Sin CDN externos (lo vigila
  `core.tests.VendorAssetsTests`).
- `ruff check .` limpio desde `backend/` (reglas E,F,W,B,DJ de `backend/ruff.toml`).
- Suite completa desde `backend/`:
  `POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test --noinput`
  (~6 min). Una etiqueta sola: añadir `administracion.test_x.ClaseTests.test_y` antes de
  `--noinput`. En Windows se omiten 6 pruebas (4 del acta, 2 de concurrencia); es lo normal.
- Lo que **no** se mueve a la base de datos: `SECRET_KEY`, credenciales de PostgreSQL,
  `PASSWORDS_ENCRYPTION_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, los
  ajustes de HTTPS y `SOPORTE_REPORTE_PUBLICO_COOLDOWN_SEGUNDOS` (nginx es la autoridad ahí).
- Vistas nuevas en `administracion/views/<área>.py`, reexportadas en
  `administracion/views/__init__.py` con `# noqa: F401`. Parchear en tests como
  `administracion.views.<submódulo>.<nombre>`.
- Toda vista nueva de solo lectura se añade a la lista de
  `core.tests.SmokeVistasTests` (`core/tests.py:423-447`).
- Toda vista con confirmación necesita una prueba que haga `GET` y renderice la plantilla.
- Campos de fecha: `forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")`.
- Esto toca permisos y sesión en las 60+ vistas: **va por PR a `master`**, para que corra
  el job `test-postgres` (el único que ejecuta las pruebas de concurrencia), antes de
  desplegar. No se despliega sin CI verde.
- **Ningún secreto en un `RegistroAuditoria` ni en un log.** Los campos de secreto se
  registran como `(cambiada)`.

## Foco de revisión

Cinco cosas que la spec implica, que ninguna tarea exigiría por sí sola y que son las que
más duelen si se rompen. Cada una tiene su prueba asignada a la tarea que posee el código.

1. **Candado sin llave.** Desactivar `administracion` o quitarle `escritura` a
   `superadmin` deja la configuración inalcanzable desde la web. Debe ser imposible, no
   advertido. → pruebas en Tarea 1 (módulo esencial) y Tarea 2 (regla de `superadmin`).
2. **Tablas de configuración vacías.** Base nueva, `migrate` a medias o caché frío no
   pueden tumbar el login: con `Modulo` y `PermisoRol` vacías todo se comporta como hoy.
   → pruebas en Tarea 1 y Tarea 2.
3. **Un rol que ya no existe.** Una cuenta cuyo `rol` no está en la tabla `Rol` (rol
   borrado, dato viejo) resuelve a `ninguno` y no revienta; y `choices` llamable no puede
   reventar `migrate` sobre una base sin la tabla. → pruebas en Tarea 2.
4. **El 404 que se come el login.** Con los 10 módulos inactivos, `/accounts/login/`,
   el tablero y los avisos siguen respondiendo 200. → pruebas en Tarea 4.
5. **La contraseña SMTP.** Guardar el formulario con el campo vacío conserva la guardada,
   y ningún `RegistroAuditoria` contiene nunca el valor. → pruebas en Tarea 3 y Tarea 10.

## Estructura de archivos

**Nuevos**

| Archivo | Responsabilidad |
| --- | --- |
| `administracion/registro.py` | lectura cacheada de `Modulo` y `PermisoRol`, e invalidación |
| `administracion/auditoria.py` | `auditar_cambios()`: diferencia de un form → auditoría, sin secretos |
| `administracion/middleware.py` | `ModuloActivoMiddleware`, `SesionConfigurableMiddleware` |
| `administracion/seguridad.py` | callables de `axes` y validador de longitud de contraseña |
| `administracion/context_processors.py` | `menu_modulos` para el sidebar |
| `administracion/views/` | paquete: `auditoria.py`, `cuentas.py`, `general.py`, `modulos.py`, `roles.py`, `correo.py`, `seguridad.py`, `datos.py`, `inicio.py` |
| `administracion/test_registro.py` · `test_modulos.py` · `test_roles.py` · `test_auditoria.py` · `test_seguridad.py` · `test_correo.py` | pruebas por área |

**Modificados**

| Archivo | Qué cambia |
| --- | --- |
| `administracion/models.py:43` | `Modulo`, `Rol`, `PermisoRol`; campos nuevos en `ConfiguracionSistema` |
| `accounts/permisos.py:19-93` | `nivel_permiso()` como único punto de lectura; `APP_A_MODULO` |
| `accounts/templatetags/permisos_extras.py:14` | pasa por `nivel_permiso` |
| `core/views.py:65` | ídem (`media_protegido`) |
| `notificaciones/services.py:28` | ídem (`_puede_ver`) |
| `accounts/models.py:5` | `rol` con `choices` llamable |
| `templates/base.html:36-115` | el menú pasa a ser un bucle sobre módulos activos |
| `sysadmin/settings/base.py:54-64,96-143` | middlewares nuevos, callables de axes, validador propio |
| `core/tests.py:181-190,423-447` | dejan de mutar `PERMISOS_POR_ROL`; la lista de humo recorre módulos activos |
| `notificaciones/management/commands/...` + `core/management/commands/limpiar_historial.py` | valores por defecto desde la configuración |

---

### Tarea 1: Catálogo de módulos

**Archivos:**
- Modificar: `administracion/models.py` (añadir al final)
- Crear: `administracion/registro.py`
- Crear: `administracion/migrations/0003_modulo.py` (esquema) y `0004_sembrar_modulos.py` (datos)
- Modificar: `accounts/permisos.py` (añadir `APP_A_MODULO`)
- Test: `administracion/test_registro.py`

**Interfaces:**
- Consume: `accounts.permisos.MODULOS` (lista de 10 claves, ya existe).
- Produce:
  - `administracion.models.Modulo` con campos `clave` (único), `nombre`, `icono`,
    `url_nombre`, `orden`, `activo`, `es_esencial`.
  - `administracion.registro.modulos_activos() -> set[str]`
  - `administracion.registro.modulo_esta_activo(clave: str) -> bool`
  - `administracion.registro.invalidar_cache() -> None`
  - `accounts.permisos.APP_A_MODULO: dict[str, str]` — `app_name` de la URL → clave de
    módulo. Las parejas que no coinciden por nombre: `reports` → `reportes`,
    `yule` → `inventario`. Las demás se mapean a sí mismas.

- [ ] **Paso 1: escribir las pruebas que fallan** en `administracion/test_registro.py`

```python
class CatalogoModulosTests(TestCase):
    def test_la_migracion_siembra_los_diez_modulos(self):
        self.assertEqual(Modulo.objects.count(), 10)
        self.assertEqual(set(Modulo.objects.values_list("clave", flat=True)), set(MODULOS))

    def test_licencias_y_prestamos_nacen_inactivos(self):
        self.assertFalse(Modulo.objects.get(clave="licencias").activo)
        self.assertFalse(Modulo.objects.get(clave="prestamos").activo)
        # los ocho restantes activos
        self.assertEqual(Modulo.objects.filter(activo=True).count(), 8)

    def test_los_esenciales_son_los_cuatro_esperados(self):
        esenciales = set(Modulo.objects.filter(es_esencial=True).values_list("clave", flat=True))
        self.assertEqual(esenciales, {"inventario", "mantenimiento", "passwords", "administracion"})

    def test_un_modulo_esencial_no_se_puede_desactivar(self):
        modulo = Modulo.objects.get(clave="administracion")
        modulo.activo = False
        with self.assertRaises(ValidationError):
            modulo.save()
        self.assertTrue(Modulo.objects.get(clave="administracion").activo)

    def test_todo_modulo_tiene_url_resoluble(self):
        for modulo in Modulo.objects.all():
            reverse(modulo.url_nombre)  # no debe lanzar NoReverseMatch

    def test_con_la_tabla_vacia_todo_se_considera_activo(self):
        """Base nueva o migración a medias no puede esconder la aplicación."""
        Modulo.objects.all().delete()
        invalidar_cache()
        for clave in MODULOS:
            self.assertTrue(modulo_esta_activo(clave))

    def test_una_clave_desconocida_no_esta_activa(self):
        self.assertFalse(modulo_esta_activo("inventado"))

    def test_guardar_un_modulo_invalida_la_cache(self):
        self.assertTrue(modulo_esta_activo("soporte"))
        Modulo.objects.filter(clave="soporte").update(activo=False)
        invalidar_cache()
        self.assertFalse(modulo_esta_activo("soporte"))

    def test_cada_app_del_urlconf_mapea_a_un_modulo_conocido(self):
        for app_name, clave in APP_A_MODULO.items():
            self.assertIn(clave, MODULOS)
```

- [ ] **Paso 2: correr y ver que falla**

Desde `backend/`:
`POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test administracion.test_registro --noinput`
Esperado: FAIL — `ImportError: cannot import name 'Modulo'`.

- [ ] **Paso 3: el modelo `Modulo` en `administracion/models.py`**

`clave` = `CharField(max_length=30, unique=True)`, `nombre`, `icono` (clase de
bootstrap-icons, p. ej. `bi-laptop`), `url_nombre` (`CharField`, el nombre con namespace
que acepta `reverse()`), `orden` = `PositiveIntegerField`, `activo` y `es_esencial` =
`BooleanField`. `Meta.ordering = ["orden", "nombre"]`.

`save()` llama a `full_clean()` y `clean()` lanza `ValidationError` si
`es_esencial and not activo`. La regla va en el modelo, no en el formulario: la spec
exige que el servicio rechace el cambio, no solo que el HTML lo deshabilite.

- [ ] **Paso 4: migración de esquema y migración de datos**

`manage.py makemigrations administracion` para el esquema. La de datos se escribe a mano
(`migrations.RunPython` con su inverso) y siembra las 10 filas. Valores exactos:

| clave | nombre | icono | url_nombre | orden | activo | es_esencial |
| --- | --- | --- | --- | --- | --- | --- |
| usuarios | Usuarios | bi-people | usuarios:lista | 10 | sí | no |
| inventario | Inventario | bi-laptop | inventario:lista | 20 | sí | **sí** |
| reportes | Reportes | bi-file-earmark-bar-graph | reports:index | 30 | sí | no |
| mantenimiento | Mantenimiento | bi-tools | mantenimiento:inicio | 40 | sí | **sí** |
| licencias | Licencias | bi-diamond | licencias:lista | 50 | **no** | no |
| prestamos | Préstamos | bi-box-arrow-in-right | prestamos:lista | 60 | **no** | no |
| documentos | Documentos | bi-folder | documentos:lista | 70 | sí | no |
| soporte | Soporte | bi-life-preserver | soporte:lista | 80 | sí | no |
| passwords | Contraseñas | bi-key | passwords:index | 90 | sí | **sí** |
| administracion | Configuración | bi-shield-lock | administracion:inicio | 100 | sí | **sí** |

`administracion:inicio` todavía no existe (se crea en la Tarea 6), así que esta tarea
siembra **`administracion:lista_auditoria`**, que sí resuelve. La Tarea 6 lo cambia con
una migración nueva. Todas las pruebas de esta tarea quedan verdes aquí.

Usa `apps.get_model`, no el import directo — si no, una migración vieja se rompe al
cambiar el modelo.

- [ ] **Paso 5: `administracion/registro.py`**

`modulos_activos()` lee de la caché con la clave `"sysadmin:modulos_activos"`; si no está,
consulta `Modulo.objects.filter(activo=True)` y la guarda. **Si la tabla está vacía
devuelve `set(MODULOS)`** (foco de revisión 2), y atrapa los errores de base de
`django.db` para que una migración a medias no tumbe el login.
`modulo_esta_activo(clave)` devuelve `False` para una clave fuera de `MODULOS`.

`invalidar_cache()` es **una sola función que limpia todas las claves de configuración**
del proyecto, no solo las de módulos: la Tarea 2 le añade la de permisos en vez de crear
un segundo invalidador. Se conecta por `post_save` y `post_delete` de `Modulo` en
`administracion/signals.py` (el archivo ya existe y `apps.py` ya lo carga).

- [ ] **Paso 6: `APP_A_MODULO` en `accounts/permisos.py`**

Debajo de `MODULOS`. Un diccionario explícito con las 10 claves más las dos parejas que
no coinciden por nombre (`reports` → `reportes`, `yule` → `inventario`).

- [ ] **Paso 7: correr las pruebas y el lint**

`... manage.py test administracion.test_registro --noinput` → PASS, las nueve.
`../.venv/Scripts/ruff.exe check .` → sin hallazgos.

- [ ] **Paso 8: commit**

```bash
git add backend/administracion backend/accounts/permisos.py
git commit -m "configuracion: catalogo de modulos en base de datos"
```

---

### Tarea 2: Matriz de permisos editable

**Archivos:**
- Modificar: `administracion/models.py`, `administracion/registro.py`
- Modificar: `accounts/permisos.py:60-93`, `accounts/models.py:5`,
  `accounts/templatetags/permisos_extras.py:14`, `core/views.py:65`,
  `notificaciones/services.py:28`
- Modificar: `core/tests.py:181-190` (deja de mutar el dict), `accounts/tests.py:29-32`
- Crear: migraciones de esquema y de datos
- Test: `administracion/test_roles.py`

**Interfaces:**
- Consume: `registro.modulo_esta_activo` (Tarea 1); `accounts.permisos.PERMISOS_POR_ROL`,
  que **se conserva** como respaldo para base vacía.
- Produce:
  - `administracion.models.Rol(clave, nombre, es_sistema, orden)`
  - `administracion.models.PermisoRol(rol, modulo, nivel)` con
    `unique_together = ("rol", "modulo")` y `nivel` en `ninguno|lectura|escritura`
  - `administracion.registro.nivel_de(rol: str, modulo: str) -> str`
  - `administracion.registro.roles_choices() -> list[tuple[str, str]]`
  - `accounts.permisos.nivel_permiso(rol: str, modulo: str) -> str` — **el único punto
    de lectura de permisos del proyecto**

- [ ] **Paso 1: escribir las pruebas que fallan** en `administracion/test_roles.py`

```python
class ResolvedorPermisosTests(TestCase):
    def test_superadmin_siempre_escritura_en_todo(self):
        PermisoRol.objects.all().delete()
        invalidar_cache()
        for modulo in MODULOS:
            self.assertEqual(nivel_permiso("superadmin", modulo), "escritura")

    def test_no_se_le_puede_quitar_escritura_a_superadmin(self):
        """La llave de repuesto no se puede tirar: anti-meta 1 de la spec."""
        rol = Rol.objects.get(clave="superadmin")
        PermisoRol.objects.filter(rol=rol, modulo="administracion").update(nivel="ninguno")
        invalidar_cache()
        self.assertEqual(nivel_permiso("superadmin", "administracion"), "escritura")

    def test_la_matriz_sembrada_reproduce_la_del_codigo(self):
        for rol, permisos in PERMISOS_POR_ROL.items():
            for modulo, nivel in permisos.items():
                if modulo in ("licencias", "prestamos"):
                    continue  # modulos inactivos: resuelven a ninguno, se prueba aparte
                self.assertEqual(nivel_permiso(rol, modulo), nivel, f"{rol}/{modulo}")

    def test_un_cambio_en_la_matriz_se_refleja(self):
        self.assertEqual(nivel_permiso("tecnico", "documentos"), "lectura")
        PermisoRol.objects.filter(rol__clave="tecnico", modulo="documentos").update(nivel="escritura")
        invalidar_cache()
        self.assertEqual(nivel_permiso("tecnico", "documentos"), "escritura")

    def test_un_modulo_inactivo_resuelve_a_ninguno_para_todos(self):
        for rol in ("superadmin", "admin", "tecnico", "lectura"):
            self.assertEqual(nivel_permiso(rol, "licencias"), "ninguno")

    def test_un_rol_desconocido_resuelve_a_ninguno(self):
        self.assertEqual(nivel_permiso("rol_borrado", "inventario"), "ninguno")

    def test_con_la_tabla_vacia_se_usa_la_matriz_del_codigo(self):
        PermisoRol.objects.all().delete()
        invalidar_cache()
        self.assertEqual(nivel_permiso("tecnico", "inventario"), "escritura")
        self.assertEqual(nivel_permiso("tecnico", "passwords"), "ninguno")

    def test_un_rol_de_sistema_no_se_puede_borrar(self):
        with self.assertRaises(ValidationError):
            Rol.objects.get(clave="superadmin").delete()
        self.assertTrue(Rol.objects.filter(clave="superadmin").exists())


class ChoicesDeRolTests(TestCase):
    def test_los_choices_salen_de_la_tabla(self):
        Rol.objects.create(clave="auditor", nombre="Auditor externo", es_sistema=False, orden=50)
        invalidar_cache()
        self.assertIn(("auditor", "Auditor externo"), roles_choices())

    def test_sin_tabla_los_choices_son_los_cuatro_de_siempre(self):
        """`choices` llamable no puede reventar migrate sobre una base sin la tabla."""
        with patch("administracion.registro.Rol.objects") as objetos:
            objetos.all.side_effect = ProgrammingError("no existe la relacion")
            claves = [c for c, _ in roles_choices()]
        self.assertEqual(claves, ["superadmin", "admin", "tecnico", "lectura"])


class PuntoUnicoDeLecturaTests(TestCase):
    def test_nadie_lee_PERMISOS_POR_ROL_fuera_del_resolvedor(self):
        """Si vuelve a haber una lectura directa, el apagado de modulos se la salta."""
        permitidos = {"accounts/permisos.py", "accounts/tests.py", "administracion/test_roles.py"}
        # recorre backend/**/*.py buscando "PERMISOS_POR_ROL" y afirma que
        # todo archivo que lo menciona esta en `permitidos` o bajo
        # administracion/migrations/ (la migracion de datos tiene que leer el
        # dict para sembrar las 40 filas: es su unico uso legitimo)
```

- [ ] **Paso 2: correr y ver que falla**

`... manage.py test administracion.test_roles --noinput` → FAIL (`ImportError: Rol`).

- [ ] **Paso 3: modelos `Rol` y `PermisoRol`, y sus migraciones**

`Rol.clave` único (`max_length=20`, el mismo largo que `CustomUser.rol`); `es_sistema`
protege el borrado (`delete()` lanza `ProtectedError` si `es_sistema`). La migración de
datos siembra los 4 roles con sus nombres de `CustomUser.ROL_CHOICES` y las 40 filas de
`PermisoRol` copiadas de `PERMISOS_POR_ROL`, con `apps.get_model`.

- [ ] **Paso 4: `nivel_de` y `roles_choices` en `administracion/registro.py`**

`nivel_de` cachea el diccionario completo `{rol: {modulo: nivel}}` bajo
`"sysadmin:permisos"` en **una** consulta, no una por celda — el menú pregunta 9 veces
por request. Tabla vacía → `PERMISOS_POR_ROL`. `roles_choices()` atrapa los errores de
`django.db` y devuelve las 4 parejas de `CustomUser.ROL_CHOICES`. Ambos se invalidan por
`post_save`/`post_delete` de `Rol` y `PermisoRol`.

- [ ] **Paso 5: `nivel_permiso` en `accounts/permisos.py`**

```python
def nivel_permiso(rol: str, modulo: str) -> str:
    """Unico punto de lectura de permisos. Orden de las reglas, que importa:
    un modulo inactivo gana sobre superadmin (asi Licencias desaparece tambien
    para el superadministrador), y superadmin gana sobre la tabla."""
```

Importa `administracion.registro` **dentro** de la función, no en la cabecera del módulo:
`administracion/models.py` ya importa `accounts.permisos.MODULOS` y un import en la
cabecera cerraría el ciclo al cargar las apps. Es el patrón que ya usa
`inventario/services.py:17`.

`tiene_permiso()` y `requiere_permiso()` pasan a llamarlo. **Cuidado con los atajos de
`is_superuser`** en `requiere_permiso:86` y `media_protegido:64`: se conservan, pero ya no
dan acceso a un módulo inactivo porque el middleware de la Tarea 4 corta antes.

- [ ] **Paso 6: migrar los tres consumidores restantes**

`permisos_extras.py:14`, `core/views.py:65` y `notificaciones/services.py:28` dejan de
indexar el dict y llaman a `nivel_permiso`. `core/tests.py:181-190` deja de mutar
`PERMISOS_POR_ROL` (ya no lo lee nadie) y cambia la fila de `PermisoRol` que corresponda.

- [ ] **Paso 7: `choices` llamable en `CustomUser.rol`**

`choices=administracion_roles_choices` donde esa función es un envoltorio de
`registro.roles_choices` que vive en `accounts/permisos.py` (para no importar
`administracion` desde `accounts/models.py`). `makemigrations` generará una migración por
el cambio de `choices`; es esperada y no toca datos.

- [ ] **Paso 8: la suite completa, no solo estas pruebas**

`POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test --noinput`
Esperado: 723 + nuevas, 6 omitidas en Windows, 0 fallos. Esta tarea toca los permisos de
todas las vistas: si algo se rompió, se rompió aquí y hay que verlo antes de seguir.
`../.venv/Scripts/ruff.exe check .` limpio.

- [ ] **Paso 9: commit**

```bash
git add backend/
git commit -m "configuracion: matriz de permisos en base de datos con resolvedor unico"
```

---

### Tarea 3: Auditoría de los cambios de configuración

**Archivos:**
- Crear: `administracion/auditoria.py`
- Test: `administracion/test_auditoria.py`

**Interfaces:**
- Consume: `administracion.services.registrar_auditoria` (ya existe, `services.py:4`).
- Produce: `auditar_cambios(usuario, form, modulo="administracion", objeto=None, ip="", secretos=())`
  → escribe un `RegistroAuditoria` por cambio con `accion="configurar"` y detalle
  `«etiqueta»: anterior → nuevo`. Devuelve el número de campos registrados.

Va antes de las pantallas porque todas la usan. Es la tarea que hace cumplible la
anti-meta 2 de la spec; si cada vista arma su propio texto, alguna acabará concatenando
un secreto.

**`auditar_cambios` es solo para guardados por `ModelForm`** (Tareas 9, 10 y la pantalla
de empresa). Los cambios que no tienen formulario —el interruptor de un módulo (Tarea 7),
una celda de la matriz (Tarea 8) y la simulación de limpieza (Tarea 11)— se auditan
llamando directamente a `registrar_auditoria(...)`, que ya existe en
`administracion/services.py:4`, con `accion="configurar"`. No se inventa un formulario
falso para poder auditar.

- [ ] **Paso 1: escribir las pruebas que fallan**

```python
class AuditarCambiosTests(TestCase):
    def test_registra_un_renglon_por_campo_cambiado(self):
        form = ConfiguracionForm({...}, instance=config)  # cambia nombre_empresa y telefono
        form.is_valid(); form.save()
        self.assertEqual(auditar_cambios(self.user, form), 2)
        detalles = list(RegistroAuditoria.objects.values_list("detalle", flat=True))
        self.assertTrue(any("REDIHOS S.A.S" in d and "Clinica X" in d for d in detalles))

    def test_un_form_sin_cambios_no_escribe_nada(self):
        self.assertEqual(auditar_cambios(self.user, form_sin_cambios), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="configurar").exists())

    def test_usa_la_etiqueta_del_campo_no_su_nombre_tecnico(self):
        # detalle contiene "Nombre de la empresa", no "nombre_empresa"

    def test_un_campo_declarado_secreto_se_registra_sin_su_valor(self):
        form = ConfiguracionForm({... "smtp_password": "Sup3rS3cr3ta!"}, instance=config)
        form.is_valid(); form.save()
        auditar_cambios(self.user, form, secretos=("smtp_password",))
        detalles = " ".join(RegistroAuditoria.objects.values_list("detalle", flat=True))
        self.assertNotIn("Sup3rS3cr3ta!", detalles)
        self.assertIn("(cambiada)", detalles)

    def test_ningun_registro_de_auditoria_contiene_el_secreto_en_claro(self):
        """Foco de revision 5. Recorre TODOS los campos de texto del registro,
        no solo `detalle`, por si alguno se cuela por otra via."""
```

- [ ] **Paso 2: correr y ver que falla** → FAIL (`ImportError: auditar_cambios`).

- [ ] **Paso 3: implementar `auditar_cambios(...)` en `administracion/auditoria.py`**

Recorre `form.changed_data`. El valor anterior sale de `form.initial`, el nuevo de
`form.cleaned_data`. La etiqueta, de `form.fields[nombre].label` o del `verbose_name`
del modelo. Un campo en `secretos` se registra como `«Contraseña SMTP»: (cambiada)` y
**ni el valor nuevo ni el anterior** entran en el texto. Un valor largo se recorta a 100
caracteres.

- [ ] **Paso 4: correr y ver que pasa.** → PASS. `ruff check .` limpio.

- [ ] **Paso 5: commit**

```bash
git add backend/administracion/auditoria.py backend/administracion/test_auditoria.py
git commit -m "configuracion: auditoria de cambios que nunca registra secretos"
```

---

### Tarea 4: Middleware de módulos inactivos

**Archivos:**
- Crear: `administracion/middleware.py`
- Modificar: `sysadmin/settings/base.py:54-64`
- Test: `administracion/test_modulos.py`

**Interfaces:**
- Consume: `registro.modulo_esta_activo`, `accounts.permisos.APP_A_MODULO` (Tarea 1).
- Produce: `administracion.middleware.ModuloActivoMiddleware` con
  `process_view(request, view_func, view_args, view_kwargs)` y la constante
  `APPS_SIEMPRE_ABIERTAS = {"admin", "accounts", "core", "notificaciones"}`.

**`process_view`, no `process_request`:** `request.resolver_match` no existe todavía en
`process_request`. `process_view` corre después de resolver la URL y antes de la vista,
que es el único punto donde se conoce el `app_name`.

- [ ] **Paso 1: escribir las pruebas que fallan**

```python
class MiddlewareModulosTests(TestCase):
    def test_un_modulo_inactivo_responde_404(self):
        self.client.force_login(self.superadmin)
        self.assertEqual(self.client.get(reverse("licencias:lista")).status_code, 404)

    def test_404_y_no_redireccion(self):
        """Una redireccion con mensaje confirma que la seccion existe."""
        resp = self.client.get(reverse("licencias:lista"))
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn("Location", resp)

    def test_tambien_404_para_el_superadministrador(self):
        # el atajo is_superuser de requiere_permiso no puede saltarselo

    def test_un_modulo_activo_responde_200(self):
        self.assertEqual(self.client.get(reverse("inventario:lista")).status_code, 200)

    def test_reactivar_vuelve_a_dar_200(self):
        Modulo.objects.filter(clave="licencias").update(activo=True)
        invalidar_cache()
        self.assertEqual(self.client.get(reverse("licencias:lista")).status_code, 200)

    def test_con_todos_los_modulos_inactivos_el_login_sigue_vivo(self):
        """Foco de revision 4: el filtro no puede dejar la aplicacion inaccesible."""
        Modulo.objects.filter(es_esencial=False).update(activo=False)
        invalidar_cache()
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)
        self.client.force_login(self.superadmin)
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("notificaciones:lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("administracion:lista_auditoria")).status_code, 200)

    def test_el_formulario_publico_de_soporte_muere_con_su_modulo(self):
        """Es parte de soporte: si soporte se apaga, su formulario publico tambien."""
        Modulo.objects.filter(clave="soporte").update(activo=False)
        invalidar_cache()
        self.assertEqual(self.client.get(reverse("soporte:reportar_publico")).status_code, 404)

    def test_una_url_sin_app_name_no_se_filtra(self):
        # /media/<ruta> y las vistas sueltas del urlconf raiz no tienen app_name
```

- [ ] **Paso 2: correr y ver que falla** → FAIL: `licencias:lista` responde 200.

- [ ] **Paso 3: implementar el middleware**

Si no hay `resolver_match`, o su `app_name` está en `APPS_SIEMPRE_ABIERTAS`, o no está en
`APP_A_MODULO`, deja pasar. Si el módulo está inactivo, `raise Http404`.

- [ ] **Paso 4: registrarlo en `MIDDLEWARE`**

Después de `AuthenticationMiddleware` y antes de `AxesMiddleware`.

- [ ] **Paso 5: arreglar `SmokeVistasTests` en esta misma tarea**

`core.tests.SmokeVistasTests` (`core/tests.py:423-447`) abre las URLs de los 10 módulos y
ahora las de Licencias y Préstamos dan 404. Pasa a saltarse las URLs cuyo módulo está
inactivo (resolviendo el módulo con `APP_A_MODULO` sobre el `app_name` de cada nombre), y
se le añade la prueba del caso contrario:

```python
def test_las_urls_de_un_modulo_inactivo_dan_404(self):
    # licencias:lista, licencias:crear, licencias:exportar_excel,
    # prestamos:lista, prestamos:crear
```

Va aquí y no en la Tarea 5 porque la restricción global exige 0 fallos: un commit sobre
una suite roja deja un punto del historial donde no se puede bisecar.

- [ ] **Paso 6: correr las pruebas y la suite completa**

`... manage.py test administracion.test_modulos --noinput` → PASS.
Luego la suite completa → **0 fallos**. `ruff check .` limpio.

- [ ] **Paso 7: commit**

```bash
git add backend/administracion backend/sysadmin/settings/base.py backend/core/tests.py
git commit -m "configuracion: 404 en las urls de un modulo inactivo"
```

---

### Tarea 5: Menú y tablero por datos

**Archivos:**
- Crear: `administracion/context_processors.py`
- Modificar: `templates/base.html:36-115`, `sysadmin/settings/base.py` (`TEMPLATES` →
  `context_processors`), `core/tests.py:423-447`
- Modificar: `core/templates/core/dashboard.html` (tarjetas de módulos inactivos)
- Test: `administracion/test_modulos.py` (ampliar), `core/tests.py`

**Interfaces:**
- Consume: `registro.modulos_activos`, `nivel_permiso` (Tareas 1 y 2).
- Produce: contexto `menu_modulos` — lista de dicts `{clave, nombre, icono, url, activo}`
  ya filtrada por los permisos del usuario, ordenada por `Modulo.orden`.

Aquí desaparecen los bloques `{% if puede_* %}` escritos a mano y el
`{% comment %}` que apaga Préstamos (`base.html:81-88`).

- [ ] **Paso 1: escribir las pruebas que fallan**

```python
class MenuPorDatosTests(TestCase):
    def test_el_menu_no_muestra_un_modulo_inactivo(self):
        html = self.client.get(reverse("core:dashboard")).content.decode()
        self.assertNotIn(reverse("licencias:lista"), html)

    def test_el_menu_respeta_los_permisos_del_rol(self):
        # tecnico: passwords es "ninguno" -> su url no aparece
    def test_el_menu_sigue_el_orden_del_catalogo(self):
        # las posiciones de los href en el html van en orden de `Modulo.orden`
    def test_el_menu_no_repite_una_consulta_por_modulo(self):
        with self.assertNumQueries(...):  # una sola, por la cache del registro
    def test_activar_un_modulo_lo_hace_aparecer_sin_reiniciar(self):
        Modulo.objects.filter(clave="licencias").update(activo=True)
        invalidar_cache()
        self.assertIn(reverse("licencias:lista"), self.client.get(reverse("core:dashboard")).content.decode())
```

`SmokeVistasTests` ya quedó arreglado en la Tarea 4; esta tarea no lo toca.

- [ ] **Paso 2: correr y ver que falla** → FAIL: el menú sigue trayendo Licencias.

- [ ] **Paso 3: el context processor y el bucle de la plantilla**

`menu_modulos` recorre `Modulo.objects.filter(activo=True)` (desde la caché del registro)
y se queda con los que dan `nivel_permiso(user.rol, clave) != "ninguno"`. Devuelve
`{}` si el usuario no está autenticado.

En `base.html` el bucle reemplaza los `{% if puede_* %}`. **Quedan fijos y fuera del
bucle**, porque no son módulos: «Página Principal» (`core`), «Notificaciones» y
«Yule (OCS)» —que pertenece a `inventario` y se sigue mostrando con
`{% tiene_permiso 'inventario' 'lectura' %}`—. El enlace de Configuración sale del bucle
como cualquier otro, con `orden=100`.

- [ ] **Paso 4: el tablero**

`core/views.py:19` cuenta datos de mantenimiento e inventario, los dos esenciales, así
que no hay nada que apagar en la consulta. En `dashboard.html`, cualquier tarjeta o
enlace a un módulo se envuelve en `{% tiene_permiso %}`, que ya devuelve `False` para un
módulo inactivo.

- [ ] **Paso 5: correr la suite completa** → PASS, 0 fallos. `ruff check .` limpio.

- [ ] **Paso 6: commit**

```bash
git add backend/
git commit -m "configuracion: menu y tablero desde el catalogo de modulos"
```

---

### Tarea 6: Portada del módulo de Configuración

**Archivos:**
- Crear: `administracion/views/` (paquete) moviendo lo de `administracion/views.py`
- Crear: `administracion/templates/administracion/inicio.html` y
  `partials/tarjeta_config.html`
- Modificar: `administracion/urls.py`, `templates/base.html` (ya por el bucle),
  la migración de datos de la Tarea 1 (`administracion:inicio`)
- Test: `administracion/test_inicio.py`

**Interfaces:**
- Produce: ruta `administracion:inicio` (`""`), vista `inicio` en
  `administracion/views/inicio.py`, reexportada en `views/__init__.py`.

- [ ] **Paso 1: partir `administracion/views.py` en paquete, sin cambiar comportamiento**

`views/auditoria.py` (`lista_auditoria`), `views/cuentas.py` (las 4 de cuentas),
`views/general.py` (`configuracion`), `views/inicio.py` (nueva). `views/__init__.py`
reexporta todo con `# noqa: F401` — `urls.py` usa `views.<nombre>`.
Correr la suite: debe seguir en 0 fallos **antes** de añadir nada. Commit aparte:
`git commit -m "configuracion: vistas de administracion en paquete"`.

- [ ] **Paso 2: escribir las pruebas que fallan**

```python
class PortadaConfiguracionTests(TestCase):
    def test_la_portada_responde_200_al_superadministrador(self):
    def test_un_tecnico_no_entra_a_la_portada(self):
        # administracion es "ninguno" para tecnico -> redirige al tablero
    def test_la_portada_enlaza_las_nueve_areas(self):
        for nombre in ("administracion:configuracion", "administracion:cuentas",
                       "administracion:lista_auditoria", "administracion:modulos",
                       "administracion:roles", "administracion:correo",
                       "administracion:seguridad", "administracion:datos",
                       "yule:configuracion"):
            self.assertIn(reverse(nombre), html)
    def test_el_enlace_del_sidebar_apunta_a_la_portada_no_a_la_auditoria(self):
        # regresion del sintoma que origino todo esto
    def test_las_tarjetas_muestran_sus_conteos(self):
        # "N activas de M" en cuentas, "N de M activos" en modulos
```

La prueba `test_todo_modulo_tiene_url_resoluble` de la Tarea 1 se cierra aquí.

- [ ] **Paso 3: correr y ver que falla** → FAIL (`NoReverseMatch: administracion:inicio`).

- [ ] **Paso 4: implementar `inicio(request)`**

`@requiere_permiso("administracion", "lectura")`. Arma la lista de tarjetas de §5.9 de la
spec con sus conteos: cuentas activas/total, módulos activos/total, correos pendientes y
con error (`NotificacionEmail.objects.filter(enviado=False)`), y la fecha del último
cambio (`ConfiguracionSistema.fecha_actualizacion`). Las rutas de las Tareas 7 a 11 no
existen todavía: crearlas en `urls.py` en esta tarea apuntando a vistas marcador que
devuelvan un `render` vacío, y rellenarlas en su tarea. Así la portada se prueba entera
de una vez.

Rutas: `modulos/`, `roles/`, `correo/`, `seguridad/`, `datos/`.

- [ ] **Paso 5: la plantilla**

Rejilla de tarjetas con las clases `sa-card` y `sa-stat-icon` que ya usa el repo
(`configuracion_form.html:16` tiene el patrón). Migaja de pan como el resto.

- [ ] **Paso 6: cambiar la fila sembrada y el sidebar**

Migración de datos nueva que pone `url_nombre="administracion:inicio"` en la fila
`administracion` (no editar la migración ya aplicada de la Tarea 1).

- [ ] **Paso 7: añadir las rutas nuevas a `SmokeVistasTests`** y correr la suite completa.

- [ ] **Paso 8: commit**

```bash
git add backend/
git commit -m "configuracion: portada con las areas de configuracion"
```

---

### Tarea 7: Pantalla de módulos

**Archivos:**
- Crear: `administracion/views/modulos.py`, `administracion/forms_modulos.py`,
  plantillas `modulos_lista.html` y `partials/fila_modulo.html`
- Test: `administracion/test_modulos.py` (ampliar)

**Interfaces:**
- Consume: `Modulo` (Tarea 1), `auditar_cambios` (Tarea 3).
- Produce: `administracion:modulos` (GET, lista) y
  `administracion:toggle_modulo` (POST, `<str:clave>`, devuelve el parcial de la fila
  para HTMX).

- [ ] **Paso 1: escribir las pruebas que fallan**

```python
class PantallaModulosTests(TestCase):
    def test_lista_los_diez_modulos(self):
    def test_desactivar_un_modulo_opcional_funciona(self):
        self.client.post(reverse("administracion:toggle_modulo", args=["soporte"]))
        self.assertFalse(Modulo.objects.get(clave="soporte").activo)
    def test_el_post_devuelve_el_parcial_de_la_fila(self):
        # HX-Request -> solo partials/fila_modulo.html
    def test_desactivar_un_esencial_se_rechaza_en_el_servidor(self):
        """La casilla deshabilitada en el HTML no es una validacion."""
        resp = self.client.post(reverse("administracion:toggle_modulo", args=["administracion"]))
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Modulo.objects.get(clave="administracion").activo)
    def test_los_cuatro_esenciales_se_rechazan(self):
        for clave in ("inventario", "mantenimiento", "passwords", "administracion"):
    def test_un_tecnico_no_puede_cambiar_un_modulo(self):
        # requiere escritura en administracion -> no cambia nada
    def test_el_cambio_queda_auditado(self):
        # RegistroAuditoria con accion="configurar" y el nombre del modulo
    def test_un_get_no_cambia_nada(self):
    def test_una_clave_inexistente_da_404(self):
```

- [ ] **Paso 2: correr y ver que falla** → FAIL.

- [ ] **Paso 3: implementar las dos vistas**

`modulos(request)` con `@requiere_permiso("administracion", "lectura")`.
`toggle_modulo(request, clave)` con `"escritura"`; solo POST; `get_object_or_404`;
si `es_esencial` responde `HttpResponseBadRequest` con la razón; si no, invierte `activo`,
guarda (el `full_clean` del modelo es la segunda barrera), audita y devuelve el parcial.

- [ ] **Paso 4: la plantilla**

Una fila por módulo: icono, nombre, interruptor `form-check form-switch` con
`hx-post`/`hx-target`. El esencial sale `disabled` con «Esencial: no se puede desactivar»
al lado — la spec pide que la razón se vea, no que el interruptor se esconda.

- [ ] **Paso 5: correr las pruebas y el lint.** → PASS.

- [ ] **Paso 6: commit**

```bash
git add backend/administracion
git commit -m "configuracion: pantalla para activar y desactivar modulos"
```

---

### Tarea 8: Pantalla de roles y permisos

**Archivos:**
- Crear: `administracion/views/roles.py`, plantillas `roles_matriz.html` y
  `partials/celda_permiso.html`
- Test: `administracion/test_roles.py` (ampliar)

**Interfaces:**
- Consume: `Rol`, `PermisoRol`, `nivel_permiso` (Tarea 2); `auditar_cambios` (Tarea 3).
- Produce: `administracion:roles` (GET) y
  `administracion:guardar_permiso` (POST, `<str:rol>/<str:modulo>/`, parcial de la celda).

- [ ] **Paso 1: escribir las pruebas que fallan**

```python
class PantallaRolesTests(TestCase):
    def test_la_matriz_trae_todos_los_modulos_y_roles(self):
    def test_guardar_una_celda_cambia_el_permiso(self):
        self.client.post(reverse("administracion:guardar_permiso", args=["tecnico", "documentos"]),
                         {"nivel": "escritura"})
        self.assertEqual(nivel_permiso("tecnico", "documentos"), "escritura")
    def test_la_columna_de_superadmin_sale_deshabilitada(self):
    def test_tocar_la_celda_de_superadmin_se_rechaza(self):
        """Foco de revision 1: la llave de repuesto no se toca ni por POST directo."""
        resp = self.client.post(reverse("administracion:guardar_permiso", args=["superadmin", "administracion"]),
                                {"nivel": "ninguno"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(nivel_permiso("superadmin", "administracion"), "escritura")
    def test_un_nivel_invalido_se_rechaza(self):
        # {"nivel": "total"} -> 400, nada cambia
    def test_el_cambio_surte_efecto_en_una_vista_de_inmediato(self):
        # el tecnico recibe 200 en una vista de escritura que antes le daba redireccion
    def test_el_cambio_queda_auditado_con_anterior_y_nuevo(self):
    def test_un_tecnico_no_puede_abrir_la_matriz(self):
```

- [ ] **Paso 2: correr y ver que falla** → FAIL.

- [ ] **Paso 3: implementar las dos vistas**

`roles(request)` arma la matriz como lista de filas (módulo) × columnas (rol) leyendo el
diccionario cacheado de una sola vez. `guardar_permiso(request, rol, modulo)` valida que
`nivel` esté en los tres válidos y que `rol != "superadmin"`, hace `update_or_create`,
audita y devuelve el parcial de la celda.

- [ ] **Paso 4: la plantilla**

Tabla con módulos en filas y roles en columnas; `<select>` de tres opciones por celda con
`hx-post` en `change`. La columna de `superadmin` se dibuja como texto fijo «Escritura
(fijo)» en gris.

- [ ] **Paso 5: correr las pruebas y el lint.** → PASS.

- [ ] **Paso 6: commit**

```bash
git add backend/administracion
git commit -m "configuracion: matriz de roles y permisos editable"
```

---

### Tarea 9: Seguridad configurable

**Archivos:**
- Modificar: `administracion/models.py` (`ConfiguracionSistema`),
  `administracion/middleware.py`, `sysadmin/settings/base.py:96-143`
- Crear: `administracion/seguridad.py`, `administracion/views/seguridad.py`,
  `administracion/forms_seguridad.py`, plantilla `seguridad_form.html`
- Test: `administracion/test_seguridad.py`

**Interfaces:**
- Produce:
  - Campos en `ConfiguracionSistema`: `sesion_minutos` (def. 30, mín. 1),
    `intentos_antes_de_bloquear` (def. 5, mín. 1), `horas_de_bloqueo` (def. 1, mín. 0),
    `longitud_minima_password` (def. 10, mín. 8)
  - `administracion.seguridad.limite_de_intentos(request, credentials) -> int`
  - `administracion.seguridad.tiempo_de_bloqueo(request) -> timedelta | None`
  - `administracion.seguridad.LongitudMinimaConfigurable` (validador de Django:
    `validate(password, user=None)` + `get_help_text()`)
  - `administracion.middleware.SesionConfigurableMiddleware`
  - `administracion:seguridad` (GET/POST)

- [ ] **Paso 1: escribir las pruebas que fallan**

```python
class SeguridadConfigurableTests(TestCase):
    def test_el_limite_de_intentos_sale_de_la_configuracion(self):
        ConfiguracionSistema.objects.filter(pk=1).update(intentos_antes_de_bloquear=3)
        self.assertEqual(limite_de_intentos(request, {}), 3)

    def test_axes_bloquea_al_numero_configurado(self):
        """La prueba que importa: que axes de verdad llame al callable."""
        ConfiguracionSistema.objects.filter(pk=1).update(intentos_antes_de_bloquear=2)
        # dos intentos fallidos -> el tercero responde con el bloqueo

    def test_el_tiempo_de_bloqueo_sale_de_la_configuracion(self):
        self.assertEqual(tiempo_de_bloqueo(None), timedelta(hours=2))

    def test_cero_horas_de_bloqueo_devuelve_None(self):
        # axes interpreta None como "sin bloqueo temporal"

    def test_la_longitud_minima_sale_de_la_configuracion(self):
        ConfiguracionSistema.objects.filter(pk=1).update(longitud_minima_password=14)
        with self.assertRaises(ValidationError):
            LongitudMinimaConfigurable().validate("Trece1234567")

    def test_el_validador_esta_conectado_en_los_settings(self):
        # validate_password("corta") falla con la longitud de la configuracion

    def test_el_middleware_fija_el_vencimiento_de_la_sesion(self):
        ConfiguracionSistema.objects.filter(pk=1).update(sesion_minutos=5)
        self.client.get(reverse("core:dashboard"))
        self.assertEqual(self.client.session.get_expiry_age(), 300)

    def test_sin_configuracion_se_usan_los_valores_de_los_settings(self):
        """Cache frio o tabla vacia no pueden dejar la aplicacion sin politica."""

    def test_el_formulario_rechaza_valores_que_dejan_fuera_al_usuario(self):
        """Foco de revision 1: un 0 en sesion_minutos cierra la sesion en el mismo
        request en que se guarda."""
        for campo, valor in (("sesion_minutos", 0), ("intentos_antes_de_bloquear", 0),
                             ("longitud_minima_password", 4)):
            # el form es invalido y el valor guardado no cambia

    def test_el_cambio_queda_auditado(self):
```

- [ ] **Paso 2: correr y ver que falla** → FAIL.

- [ ] **Paso 3: los campos y su migración**

`PositiveIntegerField` con `MinValueValidator` en cada uno, los mínimos de la tabla de
§5.7 de la spec.

- [ ] **Paso 4: `administracion/seguridad.py`**

Los tres leen `ConfiguracionSistema.get_config()` y caen a los valores de `settings` si
la lectura falla. `tiempo_de_bloqueo` devuelve `None` cuando `horas_de_bloqueo == 0`
(`axes/helpers.py:52-77` lo interpreta como «sin bloqueo temporal»).
`LongitudMinimaConfigurable` hereda de `MinimumLengthValidator` y resuelve `min_length`
en cada `validate()`, porque Django instancia el validador una sola vez.

- [ ] **Paso 5: conectar en `settings/base.py`**

`AXES_FAILURE_LIMIT = "administracion.seguridad.limite_de_intentos"` y
`AXES_COOLOFF_TIME = "administracion.seguridad.tiempo_de_bloqueo"` — **rutas con puntos,
no el callable importado**: importar `administracion` desde los settings dispara la carga
de apps antes de tiempo. `axes` resuelve la ruta con `import_string`
(`helpers.py:451-452` y `:72-74`). En `AUTH_PASSWORD_VALIDATORS` se reemplaza
`MinimumLengthValidator` por `administracion.seguridad.LongitudMinimaConfigurable`.

Dejar escrito en un comentario que esto hace desaparecer la columna de estado del
`/admin/` de axes (`axes/admin.py:45` comprueba `isinstance(..., int)`), para que no se
investigue como un error.

- [ ] **Paso 6: `SesionConfigurableMiddleware`**

`process_request`: si el usuario está autenticado, `request.session.set_expiry(minutos * 60)`.
Registrarlo después de `AuthenticationMiddleware`. `SESSION_SAVE_EVERY_REQUEST = True` ya
está puesto, así que el minutero se renueva en cada request: es inactividad real.

- [ ] **Paso 7: vista y formulario.** `@requiere_permiso("administracion", "escritura")`,
`ModelForm` sobre los cuatro campos, `auditar_cambios` al guardar.

- [ ] **Paso 8: correr la suite completa.** Esta tarea toca el login: 0 fallos antes de
seguir. `ruff check .` limpio.

- [ ] **Paso 9: commit**

```bash
git add backend/
git commit -m "configuracion: sesion, bloqueo por intentos y politica de contrasenas configurables"
```

---

### Tarea 10: Correo

**Archivos:**
- Modificar: `administracion/models.py`, `administracion/forms.py`,
  `notificaciones/services.py:254-266`
- Crear: `administracion/views/correo.py`, plantilla `correo_form.html`
- Test: `administracion/test_correo.py`

**Interfaces:**
- Consume: `notificaciones.services._get_smtp_connection` (ya existe).
- Produce:
  - Campo `correo_remitente` (`EmailField`, vacío = usar `smtp_usuario`)
  - `ConfiguracionSistema.remitente_efectivo() -> str`
  - `administracion:correo` (GET/POST), `administracion:probar_correo` (POST),
    `administracion:reintentar_correos` (POST)

- [ ] **Paso 1: escribir las pruebas que fallan**

```python
class CorreoConfiguracionTests(TestCase):
    def test_guardar_sin_contrasena_conserva_la_guardada(self):
        """Foco de revision 5. Hoy funciona (forms.py:74); esto lo fija."""
        config.set_smtp_password("original"); config.save()
        # POST del formulario completo con smtp_password=""
        self.assertEqual(ConfiguracionSistema.get_config().get_smtp_password(), "original")

    def test_la_contrasena_nueva_reemplaza_la_anterior(self):

    def test_la_contrasena_nunca_aparece_en_la_auditoria(self):
        # POST con smtp_password="Sup3rS3cr3ta!" -> ningun RegistroAuditoria la contiene

    def test_el_remitente_vacio_cae_al_usuario_smtp(self):
        self.assertEqual(config.remitente_efectivo(), config.smtp_usuario)

    def test_probar_envio_manda_un_correo_y_lo_reporta(self):
        with patch("administracion.views.correo._get_smtp_connection") as conexion:
            resp = self.client.post(reverse("administracion:probar_correo"),
                                    {"destino": "a@b.co"}, follow=True)
        self.assertContains(resp, "Correo de prueba enviado")

    def test_probar_envio_muestra_el_error_textual_del_servidor(self):
        # la conexion lanza SMTPAuthenticationError -> el mensaje llega a la pantalla

    def test_probar_envio_sin_smtp_configurado_avisa_y_no_revienta(self):
        # smtp_host vacio -> _get_smtp_connection devuelve None

    def test_el_correo_de_prueba_no_pasa_por_la_cola(self):
        self.assertEqual(NotificacionEmail.objects.count(), 0)

    def test_la_contrasena_no_aparece_en_el_mensaje_de_error(self):
        # el except no puede volcar la conexion ni sus credenciales

    def test_la_pantalla_muestra_pendientes_y_fallidos(self):
        # dos NotificacionEmail sin enviar, una con intentos=5 -> los conteos salen

    def test_reintentar_pone_los_fallidos_de_vuelta_en_la_cola(self):
        # intentos=5 -> intentos=0, error=""

    def test_un_tecnico_no_puede_probar_el_correo(self):
```

- [ ] **Paso 2: correr y ver que falla** → FAIL.

- [ ] **Paso 3: `correo_remitente`, su migración y `remitente_efectivo()`**

- [ ] **Paso 4: `timeout` en `_get_smtp_connection`**

Añadir `timeout=10` a la llamada de `get_connection` en `notificaciones/services.py:258`.
Sin él, un host inalcanzable cuelga el worker de gunicorn hasta el `GUNICORN_TIMEOUT`. Es
un arreglo real que la pantalla de prueba hace evidente: hoy nadie llama a esto desde una
petición web, solo el cron.

- [ ] **Paso 5: las tres vistas**

`correo(request)`: `ModelForm` con los campos SMTP más el remitente, los conteos de la
cola, y `auditar_cambios(..., secretos=("smtp_password",))` al guardar.
`probar_correo(request)`: solo POST; `EmailMessage` directo sobre la conexión, **sin**
pasar por `NotificacionEmail`; `except Exception` que pone `str(exc)[:500]` en un
`messages.error`. Audita la prueba con el destino, nunca con la credencial.
`reintentar_correos(request)`: pone `intentos=0` y `error=""` en los no enviados.

- [ ] **Paso 6: la plantilla.** Reaprovechar el `fieldset` «Correo SMTP» que ya existe en
`configuracion_form.html:66` y añadir el bloque de prueba y el de la cola.

- [ ] **Paso 7: correr las pruebas y el lint.** → PASS.

- [ ] **Paso 8: commit**

```bash
git add backend/
git commit -m "configuracion: remitente, probar envio y cola de correo"
```

---

### Tarea 11: Retención de datos

**Archivos:**
- Modificar: `administracion/models.py`,
  `core/management/commands/limpiar_historial.py`
- Crear: `administracion/views/datos.py`, plantilla `datos_form.html`
- Test: `administracion/test_datos.py`

**Interfaces:**
- Produce: campos `retencion_dias` (def. 365, mín. 30) y `retencion_media_dias`
  (def. 30, mín. 7); rutas `administracion:datos` (GET/POST) y
  `administracion:simular_limpieza` (POST).

> Ruta verificada: `backend/core/management/commands/limpiar_historial.py`. Sus argumentos
> actuales son `--dias` (`default=365`), `--media-dias` (`default=30`) y `--dry-run`, y
> `handle()` los lee de `options` en sus tres primeras líneas.

- [ ] **Paso 1: escribir las pruebas que fallan**

```python
class RetencionTests(TestCase):
    def test_el_comando_sin_argumentos_usa_la_configuracion(self):
        ConfiguracionSistema.objects.filter(pk=1).update(retencion_dias=90)
        # un RegistroAuditoria de hace 120 dias se borra; uno de hace 60 no

    def test_un_argumento_explicito_le_gana_a_la_configuracion(self):
        """El cron instalado pasa --dias 365: no se puede romper."""
        call_command("limpiar_historial", "--dias", "500")
        # el de 400 dias sobrevive aunque la configuracion diga 90

    def test_la_simulacion_no_borra_nada(self):
        antes = RegistroAuditoria.objects.count()
        self.client.post(reverse("administracion:simular_limpieza"))
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_la_simulacion_informa_que_borraria(self):
        # la respuesta nombra las tablas y sus conteos

    def test_el_formulario_rechaza_una_retencion_por_debajo_del_minimo(self):

    def test_un_tecnico_no_puede_simular_la_limpieza(self):
```

- [ ] **Paso 2: correr y ver que falla** → FAIL.

- [ ] **Paso 3: los campos y su migración.**

- [ ] **Paso 4: el comando lee la configuración**

Los `add_argument` pasan a `default=None` y, cuando llegan en `None`, se resuelven desde
`ConfiguracionSistema`. **El argumento explícito sigue ganando**: el cron semanal
instalado en el servidor pasa `--dias 365` y no se va a tocar.

- [ ] **Paso 5: vista y formulario.** `simular_limpieza` llama al comando con `--dry-run`
capturando su salida con `StringIO` y la muestra.

- [ ] **Paso 6: correr las pruebas y el lint.** → PASS.

- [ ] **Paso 7: commit**

```bash
git add backend/
git commit -m "configuracion: retencion de historial configurable y simulacion de limpieza"
```

---

### Tarea 12: Cierre — suite, documentación y despliegue

**Archivos:**
- Modificar: `SYSADMIN_HANDOFF.md`, `SysAdmin/AGENTS.md`, `.superpowers/sdd/` (ledger)

- [ ] **Paso 1: la suite completa y el lint**

```bash
cd backend
POSTGRES_DB= PYTHONIOENCODING=utf-8 ../.venv/Scripts/python.exe manage.py test --noinput
../.venv/Scripts/ruff.exe check .
../.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
```
Esperado: 0 fallos (6 omitidas en Windows), lint limpio, *No changes detected*.
**Si algo falla, se para y se reporta. No se despliega a medias.**

- [ ] **Paso 2: verificar a mano las cuatro cosas que ninguna prueba cubre del todo**

1. Desactivar Soporte y confirmar que desaparece del menú y que su URL da 404.
2. Reactivarlo y confirmar que vuelve con sus tickets.
3. Cambiar `sesion_minutos` a 1, esperar y confirmar que pide login otra vez.
4. Probar el correo contra el SMTP real y leer el resultado en pantalla.

- [ ] **Paso 3: documentar**

`SYSADMIN_HANDOFF.md`: entrada de changelog con la versión, qué se configura ahora desde
la pantalla y qué se quedó en el `.env` y por qué. `AGENTS.md`: tres reglas nuevas —
(a) los permisos se leen **solo** por `nivel_permiso`, nunca indexando `PERMISOS_POR_ROL`;
(b) un módulo nuevo necesita su fila en `Modulo`, su entrada en `APP_A_MODULO` y sus
filas en `PermisoRol`; (c) una vista de configuración audita con `auditar_cambios` y
declara sus campos de secreto.

- [ ] **Paso 4: PR a `master`**

Rama `feat/modulo-configuracion`. **Esperar el CI verde**, en particular el job
`test-postgres`: es el único que corre las pruebas de concurrencia y esto tocó los
permisos de todas las vistas.

- [ ] **Paso 5: desplegar**

Seguir `GUIA_DEPLOY_PASO_A_PASO.md` §8b (`git archive` con LF → `docker compose build` →
`up -d`). Respaldo antes (`.dump` fechado). Después del `migrate`, confirmar en el
contenedor que las tres tablas quedaron sembradas:

```bash
docker exec sysadmin_django python manage.py shell -c "
from administracion.models import Modulo, Rol, PermisoRol
print(Modulo.objects.count(), Rol.objects.count(), PermisoRol.objects.count())"
```
Esperado: `10 4 40`.

- [ ] **Paso 6: actualizar la memoria**

`mantenimiento-v2-en-curso.md` con la versión nueva y los pendientes que queden, y una
memoria `sysadmin-configuracion` con las tres reglas de `AGENTS.md`, que son las que se
olvidan.
