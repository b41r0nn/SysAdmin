# SysAdmin · Registro de Fases (post Etapas 0-8)

> Documento vivo: se actualiza al inicio y al cierre de cada fase.
> Fases 1 y 2 corresponden a la evolución del sistema tras la release `v1.1.0` (Etapas 0-8 + importación masiva).

---

## 📊 Tabla de Estado de Fases

| Fase | Título | Estado | Fecha | Tests |
|------|--------|--------|-------|-------|
| 1 | Módulo de Administración (roles + permisos + auditoría) | ✅ COMPLETA | 2026-09-10 | `accounts` + `administracion` |
| 2 | Etiquetas QR para activos | ✅ COMPLETA | 2026-09-10 | `inventario` (+10) |
| 3 | Mantenimiento completo: notificaciones + checklist + criticidad + calendario + reportar | ✅ COMPLETA | 2026-09-10 | `notificaciones` (31) + `mantenimiento` (+12) |
| — | Tests de cobertura (detour no planificado) | ✅ COMPLETA | 2026-09-10 | 81 tests agregados |
| 4 | Helpdesk / Tickets (app `soporte`) | ✅ COMPLETA | 2026-09-10 | `soporte` (14) → **167 en total** |
| 5 | Licencias de software (app `licencias`) | ✅ COMPLETA | 2026-09-10 | `licencias` (19) → **186 en total** |
| 6 | Préstamos de equipos (app `prestamos`) | ✅ COMPLETA | 2026-09-10 | `prestamos` (16) → **202 en total** |

---

## ✅ FASE 1 — Módulo de Administración

**Fecha:** 2026-09-10 · **Estado:** ✅ COMPLETA

### Objetivo

Establecer un sistema de **roles y permisos** centralizado, registro de **auditoría** y **configuración del sistema**, con una interfaz de administración solo para superusuarios. Fue la base que permitió restringir el acceso a todos los módulos del sistema según el rol.

### Alcance

1. **Roles de usuario** (`accounts`):
   - Nuevo campo `CustomUser.rol` con choices: `superadmin`, `admin`, `tecnico`, `lectura`.
   - Migración `accounts/0002_rol_field.py` + data migration (superusuarios existentes → `superadmin`).
   - Matriz de permisos `PERMISOS_POR_ROL` en `accounts/permisos.py` (fuente de verdad).
   - Decoradores `@requiere_permiso(modulo, nivel)` (`lectura` | `escritura`) y `@solo_superadmin`.

2. **Aplicación discrecional en todas las vistas**:
   - `usuarios`, `inventario`, `reports`, `mantenimiento`, `passwords`, `documentos`, `yule` (mapeada al módulo `inventario`).
   - Limpieza de lógica redundante (ej. `_is_admin`/`_require_admin` en `passwords`).
   - El dashboard (`core`) conserva `@login_required` (es la landing a la que redirige el decorador al denegar acceso).

3. **Nueva app `administracion`**:
   - `RegistroAuditoria`: usuario, módulo, acción, objeto, detalle, IP, fecha (+ índices). Se llena con el helper `registrar_auditoria()` y mediante signals de `login`/`logout`.
   - `ConfiguracionSistema`: datos de empresa (nombre, NIT, dirección, teléfono, correo, firma de reportes). Singleton (pk=1) con `get_config()`.
   - Vistas: `auditoria/` (filtros por módulo/acción/texto + paginación) y `configuracion/` (solo superadmin).
   - Template tag `tiene_permiso` (`accounts/templatetags/permisos_extras.py`) + **sidebar condicional por rol** en `base.html`.

4. **Desbloqueo de herramientas locales**: `import weasyprint` movido a import local dentro de las funciones PDF (`generar_acta_pdf`, `inventario_pdf`, `usuarios_pdf`) → `makemigrations`, `manage.py check` y los tests corren sin GTK en Windows.

### Archivos clave

- `backend/accounts/permisos.py`, `backend/accounts/models.py`, `backend/accounts/migrations/0002_rol_field.py`
- `backend/accounts/templatetags/permisos_extras.py`
- `backend/administracion/` (models, services, signals, forms, views, urls, admin, templates, `migrations/0001_initial.py`)
- `backend/inventario/views.py`, `backend/reports/views.py` (lazy import weasyprint)
- Vistas decoradas: `usuarios`, `inventario`, `reports`, `mantenimiento`, `passwords`, `documentos`, `yule`
- `backend/sysadmin/settings/base.py` (INSTALLED_APPS), `backend/sysadmin/urls.py` (include administracion)
- `backend/templates/base.html` (sidebar)

### Migraciones

- `accounts/0002_rol_field.py`, `administracion/0001_initial.py`

### Dependencias

- Ninguna nueva (se usa Django estándar + las ya existentes).

### Tests

- `accounts/tests.py` (matriz de permisos, acceso por rol, redirect a login, tag de template).
- `administracion/tests.py` (`ConfiguracionSistema`, `RegistroAuditoria`, signals de login/logout, permisos de vistas).

### Notas / deuda técnica

- La `db.sqlite3` local tiene un historial de migraciones inconsistente pre-existente (admin antes que accounts). Las migraciones de Fase 1 se generaron con un settings temporal apuntando a una SQLite fresca.
- El acceso a `passwords` en escritura queda efectivamente solo para `superadmin` (admin = solo lectura).

---

## ✅ FASE 2 — Etiquetas QR para activos

**Fecha:** 2026-09-10 · **Estado:** ✅ COMPLETA

### Objetivo

Imprimir **etiquetas físicas** con código QR para los activos de inventario, que al escanearse abran la ficha del activo. Generadas como PDF imprimible (92×58 mm), individual o en masa.

### Alcance

1. **Dependencia nueva**: `qrcode==8.2` (generación de QR en PNG puro, sin GTK).
2. **Contenido del QR**: URL absoluta de la ficha (`/inventario/<pk>/`) construida con `request.build_absolute_uri`.
3. **Endpoints nuevos** en `inventario` (todos `@requiere_permiso("inventario", "lectura")`):
   - `GET /inventario/<pk>/qr/` → PNG del código QR (vista previa en la ficha).
   - `GET /inventario/<pk>/etiqueta/` → PDF de etiqueta individual.
   - `GET/POST /inventario/etiquetas/` → página de selección masiva → PDF con hasta 8 etiquetas por hoja A4.
4. **Plantillas**:
   - `inventario/etiqueta_pdf.html`: standalone WeasyPrint (patrón de `acta_pdf.html`). Cabecera con `ConfiguracionSistema.nombre_empresa` y NIT (de la Fase 1).
   - `inventario/etiquetas_seleccion.html`: web con checkboxes, selector "todos" y contador de selección.
5. **Integración UI**: botón "Etiquetas QR" en la lista, icono QR por fila en la tabla (HTMX partial), vista previa del QR + botón "Etiqueta QR" en el detalle del activo.

### Archivos clave

- `backend/inventario/views.py` (`_qr_png_bytes`, `_qr_data_uri`, `_etiqueta_context`, `_render_etiquetas_pdf`, `qr_imagen`, `qr_etiqueta_pdf`, `qr_etiquetas_masivas`)
- `backend/inventario/templates/inventario/etiqueta_pdf.html`, `etiquetas_seleccion.html`
- `backend/inventario/urls.py` (rutas `qr_imagen`, `etiqueta`, `etiquetas`)
- Botones: `inventario/templates/inventario/lista.html`, `partials/tabla.html`, `detalle.html`

### Migraciones

- Ninguna (no se agregaron campos nuevos).

### Dependencias

- `qrcode==8.2` (agregada a `requirements.txt`).

### Tests

- `inventario/tests.py` (10 nuevos): permisos, PNG válido, PDF con WeasyPrint mockeado (no requiere GTK en local), selección masiva, render real de la plantilla con QR.

### Notas

- El QR apunta a la ficha del activo; para abrirla se requiere sesión (sistema interno/LAN).
- El PDF de etiquetas se genera con el mismo patrón WeasyPrint lazy-import usado en actas y reportes.

---

## ✅ FASE 3 — Mantenimiento completo: notificaciones + checklist + criticidad + calendario + reportar

**Fecha:** 2026-09-10 · **Estado:** ✅ COMPLETA

### Objetivo

Completar el módulo de mantenimiento con sistema de notificaciones, checklist de actividades por orden, indicador de criticidad, vista de calendario y portal de reporte de fallas accesible a cualquier usuario autenticado.

### Alcance

1. **Sistema de notificaciones (app `notificaciones`):**
   - Modelo `Notificacion` con uniqueConstraint `(usuario, tipo, objetokey)` (idempotente).
   - Detectores: garantía 30 días, mantenimiento 7 días, actas sin firma, OCS sin vincular.
   - Campana HTMX en sidebar. Management command `generar_notificaciones_mantenimiento` (ejecutable vía cron/Celery beat).
2. **Checklist por orden (modelo `ChecklistItem`):**
   - Plantilla en `PlanMantenimiento` que se copia automáticamente al crear una `OrdenMantenimiento` con plan asociado.
   - Toggle completado vía HTMX sin recarga de página, con barra de progreso en el detalle de la orden.
3. **Criticidad de planes:** Campo `criticidad` (`baja/media/alta`) en `PlanMantenimiento` con badge de color en la tabla de planes.
4. **Estado `reportada`:** Nuevo estado en `OrdenMantenimiento` para ordenes creadas vía el portal de reporte.
5. **Vista de calendario:** FullCalendar CDN + endpoint JSON `/mantenimiento/calendario/eventos/` mostrando ordenes (por fecha de apertura) y planes preventivos (por proxima ejecucion) con colores por estado/criticidad.
6. **Portal de reporte de fallas:** `/mantenimiento/reportar/` accesible a cualquier usuario autenticado (`@login_required`, sin `@requiere_permiso`). Crea una `OrdenMantenimiento` con estado `reportada`, tipo `correctivo` y prioridad `alta`.
7. **Tests de Fase 3:** 12 tests — checklist plan→orden (3), toggle HTMX, management command idempotente, portal de reporte (acceso, creación, permisos, validación), calendario vista + JSON.

### Archivos clave

- `backend/mantenimiento/models.py` — `ChecklistItem`, `criticidad` en `PlanMantenimiento`, `reportada` en `ESTADOS_ORDEN`
- `backend/mantenimiento/views.py` — `_guardar_checklist_items`, `_copiar_checklist_plantilla`, `toggle_checklist`, `calendario`, `calendario_eventos`, `reportar`
- `backend/mantenimiento/forms.py` — `ChecklistItemForm`, `ReporteFallaForm`
- `backend/mantenimiento/management/commands/generar_notificaciones_mantenimiento.py`
- `backend/notificaciones/services.py` — `generar_mantenimiento()`, `generar_notificaciones_mantenimiento()`
- Templates: `calendario.html`, `form_reporte.html`, `partials/checklist_orden.html`, `partials/tabla_planes.html` (columna criticidad)
- `backend/templates/base.html` — enlace "Reportar falla" en sidebar (visible a todos los usuarios autenticados)

### Migraciones

- `mantenimiento/0002_planmantenimiento_criticidad_and_more.py` — campo `criticidad`, nuevo estado `reportada`, modelo `ChecklistItem`
- `notificaciones/0001_initial.py` (ya existía)

### Dependencias

- `fullcalendar@6.1.10` (CDN, sin dependencia pip)

### Notas

- Las migraciones de Fase 3 se generaron con un settings temporal (`sysadmin.settings._tmp_scratch` — efímero, eliminado tras uso) apuntando a una SQLite temporal fresca para evitar el historial inconsistente pre-existente en `db.sqlite3`.
- El detector de actas contenía un bug corregido en sesiones anteriores: `escaneado_firmado__isnull=True` solo detecta SQL NULL; FileField almacena `""` por defecto. Corregido a `Q(escaneado_firmado="") | Q(escaneado_firmado__isnull=True)`.
- El `checklist` al crear una orden se copia SOLO si la orden tiene un plan asociado y el POST incluye el management form del checklist (`form-TOTAL_FORMS`); POSTs externos (API, test legacy) omiten el formset sin error.
- El enlace "Reportar falla" en el sidebar no tiene `@requiere_permiso` — está visible para cualquier usuario autenticado, independientemente de su rol.

---

## ✅ FASE 4 EXTRA (detour fuera del plan) — Tests de cobertura

**Fecha:** 2026-09-10 · **Estado:** ✅ COMPLETA

### Objetivo

Cerrar la deuda de cobertura de tests: las apps `core`, `usuarios`, `mantenimiento`, `documentos`, `passwords`, `reports` y `yule` no tenían tests (o un placeholder vacío). Se escribieron tests CRUD, de permisos y de vistas para las 7 apps, y se corrigieron **2 bugs reales de producción** descubiertos durante la escritura.

### Alcance

1. **Tests nuevos por app** (81 tests agregados en Fase 4):
   - `core/tests.py` (3): dashboard `@login_required`, status 200, variables de contexto.
   - `usuarios/tests.py` (12): login required, CRUD lista/detalle/crear/editar/toggle, plantilla Excel, permisos lectura/tecnico.
   - `mantenimiento/tests.py` (16): CRUD planes (crear, toggle, eliminar con/sin órdenes), órdenes (crear, cerrar, cerrar ya cerrada, eliminar), repuestos (crear/editar/eliminar), permisos.
   - `documentos/tests.py` (11): CRUD documentos y categorías, protección de categorías con documentos, permisos.
   - `passwords/tests.py` (17): CRUD vaults y credenciales, cifrado Fernet (`set_secret`/`get_secret`), acceso con código Argon2, secreto con código correcto/incorrecto, export Excel, logs, permisos.
   - `reports/tests.py` (12): index, 5 exportaciones Excel, 2 PDF con WeasyPrint mockeado, permisos.
   - `yule/tests.py` (10): models, dashboard, lista/detalle/sin-match/historial, permisos. Reemplaza el placeholder de 1 test.

2. **Bugs reales corregidos durante los tests**:
   - `passwords/views.py` (`vault_eliminar`, `credencial_eliminar`): `_log_action` se llamaba **después** de `delete()`, por lo que el `AccesoLog` apuntaba a un objeto borrado → `ValueError: save() prohibited...`. Se movió el log antes del borrado.
   - Datos de formulario que faltaban campos `required` por convención Django (campo con `blank=False` y `default` sigue siendo obligatorio en ModelForm): `estado` en usuarios y planes, `orden` en repuestos y categorías.

3. **Mockeo de WeasyPrint**: los PDF de `reports` importan `weasyprint` de forma lazy dentro de la función, así que el mock se inyecta con `patch.dict("sys.modules", {"weasyprint": _FakeWeasyprint})` (misma técnica usada en Fase 2).

### Archivos clave

- `backend/{core,usuarios,mantenimiento,documentos,passwords,reports,yule}/tests.py`
- `backend/passwords/views.py` (fix: orden de `_log_action` vs `delete()`)

### Migraciones

- Ninguna.

### Dependencias

- Ninguna nueva.

### Tests

- Suite completa: **153/153 tests OK** (81 Fase 4 + 31 Fase 3 notificaciones + 12 Fase 3 checklist/calendario/reportar + 29 Fases 1-2).
- `manage.py check` 0 issues. Sin GTK requerido (WeasyPrint mockeado / lazy import).

### Notas

- ~~No se aplicó el drift de índices de `yule`~~ → **RESUELTO el 2026-09-10**: se generaron y aplicaron `yule/0002` (renombres de índices) y `administracion/0002` (choices de `modulo` con los módulos nuevos). `makemigrations --check` → *No changes detected*.
- No se hizo ningún commit; los cambios quedan en el working tree.

---

## ✅ FASE 4 (plan original) — Helpdesk / Tickets de soporte (app `soporte`)

**Fecha:** 2026-09-10 · **Estado:** ✅ COMPLETA

### Objetivo

Agregar un sistema de tickets/helpdesk donde cualquier usuario autenticado pueda reportar una solicitud de soporte, un técnico la asigne y/o la escale a una orden de mantenimiento vinculada.

### Alcance

1. **Nuevo módulo `soporte` en la matriz de permisos** (`accounts/permisos.py`): `superadmin`/`admin`/`tecnico` = escritura; `lectura` = lectura. `crear_ticket` usa `@login_required` (portal abierto a cualquier usuario autenticado).
2. **Modelo `Ticket`**: `asunto`, `descripcion`, `prioridad` (baja/media/alta), `estado` (abierto/en_proceso/resuelto/cerrado/escalado), `solicitante` FK (PROTECT), `asignado_a` FK (SET_NULL), timestamps. Índice `(estado, fecha_creacion)`.
3. **Vistas**: `lista_tickets` (filtros estado/prioridad/búsqueda), `crear_ticket` (portal), `detalle_ticket`, `editar_ticket`, `asignar_ticket` (POST → asigna, pasa a en_proceso y crea notificación tipo `aviso` idempotente vía `aviso_usuario`), `cambiar_estado` (resolver/cerrar), `escalar_ticket` (POST → crea `OrdenMantenimiento` correctiva/abierta con FK `ticket`, prioridad heredada del ticket).
4. **FK opcional `ticket` en `OrdenMantenimiento`** (SET_NULL, related_name `ordenes`).
5. **Notificación al asignar**: reutiliza `notificaciones.services.aviso_usuario` (`get_or_create` por objetokey `ticket:{pk}` → no duplica al reasignar).
6. **Sidebar**: enlace "Soporte" visible con `tiene_permiso 'soporte' 'lectura'`.
7. **Tests**: 14 tests en `soporte/tests.py` — login, CRUD, permisos por rol (lectura ve/crea pero no asigna/escala), notificación al asignar (e idempotencia), escalamiento a orden única.

### Archivos clave

- `backend/soporte/` (models, forms, views, urls, admin, tests, templates, migrations)
- `backend/mantenimiento/models.py` (FK `ticket` en `OrdenMantenimiento`)
- `backend/accounts/permisos.py` (módulo `soporte`)
- `backend/notificaciones/services.py` (`aviso_usuario`)
- `backend/templates/base.html` (sidebar → Soporte)
- `backend/sysadmin/settings/base.py` + `backend/sysadmin/urls.py` (INSTALLED_APPS + include)

### Migraciones

- `soporte/0001_initial.py` (modelo `Ticket`)
- `mantenimiento/0003_ordenmantenimiento_ticket.py` (FK `ticket`)

### Dependencias

- Ninguna nueva.

### Tests

- Suite completa: **167/167 tests OK** (153 previos + 14 de `soporte`).
- `manage.py check` 0 issues.

### Notas

- Migraciones generadas con el mismo workaround de BD temporal (`_tmp_scratch`) por el historial inconsistente pre-existente de `db.sqlite3`.
- `crear_ticket` no exige permiso de módulo: cualquier usuario autenticado abre el portal; `detalle`/`lista` exigen `soporte` lectura, y asignar/editar/escalar exigen escritura.
- No se hizo ningún commit; los cambios quedan en el working tree.

---

## ✅ FASE 5 — Licencias de software (app `licencias`)

**Fecha:** 2026-09-10 · **Estado:** ✅ COMPLETA

### Objetivo

Módulo dedicado a la gestión de licencias de software: registro de producto, clave/serial, tipo de cobertura, vencimiento y equipos cubiertos, con reporte Excel/PDF usando el patrón `CAMPOS_*` extensible.

### Alcance

1. **Modelo `LicenciaSoftware`**: nombre, versión, proveedor, clave/serial, tipo (`volumen/individual/oem/suscripcion`), cantidad (usuarios/equipos), fecha compra/vencimiento, costo, estado manual (`activa/cancelada`), responsable, `activos` M2M a `inventario.Activo`, observaciones, timestamps.
2. **Estado efectivo calculado** (`estado_efectivo`): `cancelada` tiene prioridad; si `fecha_vencimiento` pasó → `vencida`; ≤7 días → `por_vencer`; default → `activa`.
3. **CRUD**: lista con filtros (q/tipo/estado efectivo vía filtrado en Python) + estadísticas; detalle con M2M de equipos y links de acción; crear/editar/eliminar con confirmación.
4. **Exportación Excel** (`openpyxl`, headers REDIHOS azul) + **PDF** (`weasyprint`, lazy import, badge de estado coloreado + resumen estadístico) — ambos reutilizan `CAMPOS_LICENCIAS` (mismo patrón que `CAMPOS_INVENTARIO` de reports).
5. **Permisos**: módulo `licencias` añadido a `PERMISOS_POR_ROL` (superadmin/admin escritura; tecnico/lectura lectura). Sidebar "Licencias" entre Mantenimiento y Documentos.
6. **Filtro genérico `get_item`** para dicts en plantillas (`accounts/templatetags/permisos_extras.py`).
7. **Tests**: 19 tests — login required, CRUD (lista/crear/editar/detalle con M2M), estado efectivo (sin vencimiento, vencida, por vencer, cancelada + filtro lista por estado efectivo), permisos por rol (lectura ve pero no escribe; tecnico solo lectura), export Excel, export PDF (weasyprint mockeado), eliminar.

### Archivos clave

- `backend/licencias/` (models, forms, views, urls, admin, tests, templates, migrations)
- `backend/accounts/permisos.py` (módulo `licencias` añadido a `MODULOS`)
- `backend/accounts/templatetags/permisos_extras.py` (filtro `get_item`)
- `backend/templates/base.html` (sidebar → Licencias)
- `backend/sysadmin/settings/base.py` + `backend/sysadmin/urls.py` (INSTALLED_APPS + include)

### Migraciones

- `licencias/0001_initial.py` — modelo `LicenciaSoftware` con M2M a `inventario.Activo`.

### Dependencias

- Ninguna nueva (weasyprint ya estaba instalado; `openpyxl` ya era dependencia).

### Tests

- Suite completa: **186/186 tests OK** (167 previos + 19 de `licencias`).
- `manage.py check` 0 issues.

### Notas

- El filtrado por estado efectivo (calculado en Python a partir de `fecha_vencimiento`) se hace sobre la lista resultante en lugar de con Filtros ORM, ya que el campo es una property computada; aceptable para volumen de uso interno.
- El patrón `CAMPOS_*` es idéntico al usado en `reports/views.py` para facilitar exportar columnas a futuro sin cambiar la vista.
- No se hizo ningún commit; los cambios quedan en el working tree.

---

## ✅ FASE 6 — Préstamos de equipos (app `prestamos`)

**Fecha:** 2026-09-10 · **Estado:** ✅ COMPLETA

### Objetivo

Control de salidas temporales de inventario a usuarios internos, con detección de vencimientos y registro de devoluciones, preservando el historial completo sin eliminar registros.

### Alcance

1. **Modelo `Prestamo`**: `activo` FK a `inventario.Activo` (PROTECT), `solicitante` FK a usuario (PROTECT), `fecha_prestamo` (default hoy), `fecha_devolucion_prevista`, `fecha_devolucion`, `destino`, `observaciones`, timestamps. Índice `(fecha_prestamo, fecha_devolucion_prevista)`.
2. **Estado calculado** (`estado`): `devuelto` si hay devolución; `vencido` si la prevista está en el pasado; si no, `activo`. `dias_retraso` para vencidos.
3. **Validación**: `PrestamoForm.clean_activo` impide abrir un segundo préstamo vigente del mismo equipo; `clean_fecha_devolucion_prevista` exige prevista ≥ préstamo.
4. **Vistas**: lista con filtros (búsqueda serial/marca/destino/usuario + estado) y estadísticas; detalle con acción "Registrar devolución" (POST idempotente); crear/editar. **Sin eliminar** (historial).
5. **Permisos**: módulo `prestamos` en `PERMISOS_POR_ROL` (superadmin/admin/tecnico escritura; lectura lectura). Sidebar "Préstamos" tras Licencias.
6. **Tests**: 16 tests — login required, CRUD, rechazo de préstamo vigente, estados (activo/devuelto/vencido + retraso), filtro por estado en lista, permisos por rol (lectura no escribe; tecnico escribe).

### Archivos clave

- `backend/prestamos/` (models, forms, views, urls, admin, tests, templates, migrations)
- `backend/accounts/permisos.py` (módulo `prestamos` añadido a `MODULOS`)
- `backend/templates/base.html` (sidebar → Préstamos)
- `backend/sysadmin/settings/base.py` + `backend/sysadmin/urls.py` (INSTALLED_APPS + include)

### Migraciones

- `prestamos/0001_initial.py` — modelo `Prestamo` con FK a `inventario.Activo` y `settings.AUTH_USER_MODEL`.

### Dependencias

- Ninguna nueva.

### Tests

- Suite completa: **202/202 tests OK** (186 previos + 16 de `prestamos`).
- `manage.py check` 0 issues.

### Notas

- **Plan por fases completado**: Fases 1-6 del roadmap original quedan cerradas.
- No se hizo ningún commit; los cambios quedan en el working tree.