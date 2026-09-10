# Resumen de Sprint — SysAdmin
**Fecha:** 10 de septiembre de 2026  
**Versión al cierre:** `v1.8.1`  
**Estado:** Etapas 0-8 ✅ · Plan por fases 1-6 ✅ COMPLETO  
**Commits:** NINGUNO — todos los cambios quedan en el working tree (55 archivos, ver §13)

---

## 1. Resumen Ejecutivo

Se completó **el plan por fases completo (1-6)** del sistema SysAdmin sobre la base ya establecida (Etapas 0-8). El sprint agregó **4 módulos nuevos** (Administración, Helpdesk/Tickets, Licencias, Préstamos), **2 módulos ampliados** (QR y Mantenimiento), una capa transversal de **roles y permisos**, y una **batería de tests** que lleva la suite de 81 → **202 tests OK**.

Además se **corrigió infraestructura local**: la base `db.sqlite3` de desarrollo estaba en un estado inconsistentemente migrado desde hacía tiempo (sin `accounts_customuser`, historial roto, sin datos); se reconstruyó de cero y se resolvió el drift de migraciones pendiente (`yule` + `administracion`). `makemigrations --check` → *No changes detected*.

Metodología transversal del sprint:

- **Permisos primero**: matriz `PERMISOS_POR_ROL` y decorador `@requiere_permiso(módulo, nivel)` aplicado en todas las vistas; UI condicionada con template tag `tiene_permiso`.
- **Tests por fase**: cada fase entrega sus tests; la suite completa se valida al cierre.
- **Sin borrado lógico de históricos**: `prestamos` y `soporte` no exponen eliminar; se preserva trazabilidad.
- **Todo documentado**: `README.md`, `SYSADMIN_HANDOFF.md` y `FASES.md` reflejan cada fase.
- **ADVERTENCIA DE GIT**: por regla del proyecto, **no se ejecutó ningún commit**; el arquitecto debe decidir el agrupamiento de commits.

---

## 2. Fase 1 — Módulo de Administración (roles + permisos + auditoría) ✅

**Qué:** capa transversal de seguridad y gobernanza.

- **Roles**: `CustomUser.rol` (`superadmin` / `admin` / `tecnico` / `lectura`) en `accounts`. Migración `accounts/0002_rol_field` (campo + data migration para asignar rol default).
- **Matriz de permisos**: `accounts/permisos.py` → `MODULOS` (lista ordenada de módulos y etiquetas) + `PERMISOS_POR_ROL` (rol → módulo → nivel).
- **Decorador** `@requiere_permiso(modulo, nivel)` en todas las vistas (usuarios, inventario, reports, mantenimiento, passwords, documentos, yule→inventario, y los módulos nuevos de Fases 4-6). Autoriza **solo por `rol`** (`PERMISOS_POR_ROL`), **sin fallback por `is_superuser`**. La migración `accounts/0002` asigna `rol='superadmin'` a los superusuarios existentes en el momento de migrar; un superusuario creado después nace con el default `'tecnico'` y hay que asignarle `superadmin` manualmente (ver Riesgos §14).
- **Modelo de auditoría** `RegistroAuditoria` (app `administracion`): fecha, usuario, módulo, acción, objeto, IP. Signals de **login/logout** + `registrar_auditoria()` usado en las vistas principales.
  - ⚠️ **Efecto colateral detectado y resuelto**: los choices de `modulo` se generan dinámicamente desde `MODULOS`. Al crecer `MODULOS` en Fases 4-6, Django reportaba drift → se generó `administracion/0002_alter_registroauditoria_modulo`.
- **`ConfiguracionSistema`** singleton (self-healing con `get_config()`): usado en etiquetas QR y actas.
- **Templates**: template tag `tiene_permiso` + sidebar condicional por rol. `administracion/auditoria_lista.html` con filtros (módulo/acción/q) y paginación.

---

## 3. Fase 2 — Etiquetas QR para activos ✅

**Qué:** etiqueta PDF individual y masiva por activo.

- **Dependencia nueva**: `qrcode==8.2` agregada a `requirements.txt` (PNG puro, sin GTK). → en servidor se debe **reconstruir la imagen Docker** (`pip install`).
- QR cifra la **URL absoluta** de la ficha del activo.
- **Endpoints** (en `inventario`, `@requiere_permiso("inventario","lectura")`):
  - `GET /inventario/<pk>/qr/` → PNG
  - `GET /inventario/<pk>/etiqueta/` → PDF individual 92×58 mm
  - `GET/POST /inventario/etiquetas/` → selección masiva → PDF con hasta 8 etiquetas por hoja A4
- **Plantillas**: `etiqueta_pdf.html` (standalone WeasyPrint, patrón `acta_pdf.html`) y `etiquetas_seleccion.html` (checkboxes + contador + "todos").
- **Integración**: botón en lista, icono QR por fila y vista previa en detalle.

---

## 4. Fase 3 — Mantenimiento completo (notificaciones + checklist + criticidad + calendario + portal de reporte) ✅

**Qué:** cierre funcional del módulo de mantenimiento.

- **App `notificaciones`**: modelo `Notificacion`; **detectores perezosos** (garantía, mantenimiento, actas, OCS) ejecutados al ver la bandeja; vista bandeja/cantidad/marcar_leida; campana en sidebar (HTMX). Maintainer command `generar_notificaciones_mantenimiento`. Fix `_detectar_actas` (detecta `""` además de NULL).
- **Checklist**: `ChecklistItem` (plantilla en `PlanMantenimiento` → **copiada a la orden al crearla**); formset en crear/editar plan; toggle completado vía HTMX (partial `checklist_orden.html`) con barra de progreso.
- **Criticidad**: campo `criticidad` (baja/media/alta) en `PlanMantenimiento` con badge por color.
- **Estado `reportada`** añadido a `OrdenMantenimiento`.
- **Calendario**: FullCalendar (CDN) + endpoint JSON `calendario_eventos` con colores por estado/criticidad.
- **Portal de reporte** `/mantenimiento/reportar/`: `@login_required` **sin permiso de módulo** (cualquier usuario autenticado puede reportar), crea orden `reportada`/`correctivo`/`alta`. Enlace visible en sidebar para todos.
- Migraciones: `mantenimiento/0002` (criticidad + checklist + estado reportada + calendario) y `mantenimiento/0003` (FK `ticket` en `OrdenMantenimiento` — enlace con soporte, Fase 4).
- **Pruebas**: 12 tests (checklist plan→orden, toggle, command idempotente, portal 4, calendario).

---

## 5. Fase 4 — Helpdesk / Tickets de soporte (app `soporte`) ✅

**Qué:** mesa de ayuda para reportes de falla internos.

- **Modelo `Ticket`** (esquema real, ver `soporte/models.py`): `asunto`, `descripcion`, `prioridad` (baja/media/alta), `estado` (abierto/en_proceso/resuelto/cerrado/**escalado**), `solicitante` FK (PROTECT), `asignado_a` FK (SET_NULL), fechas. **No** tiene `severidad`, **no** tiene modelo `Comentario` ni hilo, **no** tiene campo `activo`, **no** tiene adjunto.
- **Flujo**: crear ticket (o desde el portal de reporte, que además crea `OrdenMantenimiento` con FK `ticket`) → estados `abierto/en_proceso/resuelto/cerrado` → **Escalar a orden de mantenimiento**: vista `escalar_ticket` valida que no exista una orden vinculada (`ticket.ordenes.first()`), pide el **activo en un formulario** (el ticket no lleva activo), y crea la orden con `ticket` FK, `tipo=correctivo`, `estado=abierta`, `prioridad` prellenada desde el ticket, técnico y descripción prefijada; deja el ticket en `estado='escalado'` y redirige a la orden.
- **Vistas**: lista (filtros por estado/prioridad/búsqueda), detalle (asignar, resolver/cerrar, **escalar**, editar), crear, editar. Permisos: escritura admin/tecnico, lectura al resto; crear ticket abierto a cualquier usuario autenticado.
- **Integración**: módulo `soporte` en `PERMISOS_POR_ROL`; sidebar "Soporte"; FK desde mantenimiento para que un falla reportada pueda convertirse en ticket.
- Migración `soporte/0001_initial`; 14 tests aplicables → suite 167.

---

## 6. Fase 5 — Licencias de software (app `licencias`) ✅

**Qué:** control de licencias con aviso de vencimiento y exportación.

- **Modelo `LicenciaSoftware`**: nombre, versión, proveedor, clave, tipo (volumen/individual/OEM/suscripción), cantidad, fechas de compra/vencimiento, costo, estado, responsable, observaciones, **M2M `activos`** a `inventario.Activo`, timestamps.
- **Estado efectivo computado** (`estado_efectivo`, property en Python): `cancelada > vencida > por_vencer (≤7 días) > activa` (`DIAS_AVISO_VENCIMIENTO = 7`). El filtrado por estado se hace **sobre la lista en Python** (no ORM) porque es derivado; aceptable para volumen interno.
- **Vistas**: CRUD completo, filtros (búsqueda + estado), **exportar Excel y PDF** reutilizando el patrón `CAMPOS_*` de `reports` y WeasyPrint (import lazy).
- **Permisos**: módulo `licencias` → superadmin/admin escritura; tecnico/lectura lectura.
- **Sidebar**: enlace "Licencias" tras Mantenimiento.
- **Detalle técnico**: filtro genérico **`get_item`** añadido a `accounts/templatetags/permisos_extras.py` para acceder a dicts por clave en templates (usado en listas filtrables).
- Migración `licencias/0001_initial`; 19 tests → suite 186.

---

## 7. Fase 6 — Préstamos de equipos (app `prestamos`) ✅

**Qué:** control de salidas temporales de inventario con detección de vencimientos.

- **Modelo `Prestamo`**: activo FK a `inventario.Activo` (**PROTECT**), solicitante FK a usuario (**PROTECT**), `fecha_prestamo` (default hoy), `fecha_devolucion_prevista`, `fecha_devolucion`, `destino`, `observaciones`, timestamps; índice `(fecha_prestamo, fecha_devolucion_prevista)`.
- **Estado calculado**: `devuelto > vencido (prevista en el pasado) > activo`; `dias_retraso` para vencidos. Filtro por estado sobre lista Python (mismo patrón que licencias).
- **Validación en formulario**: `clean_activo` impide un **segundo préstamo vigente** del mismo equipo; `clean_fecha_devolucion_prevista` exige prevista ≥ préstamo.
- **Registrar devolución** (POST idempotente) — **no existe eliminar**: el préstamo queda como histórico (metodología transversal "nunca borrar registros transaccionales").
- **Vistas**: lista con filtros y estadísticas (total/activos/vencidos/devueltos), detalle, crear, editar, devolver.
- **Permisos**: módulo `prestamos` → superadmin/admin/tecnico escritura; lectura lectura. Sidebar "Préstamos" tras Licencias.
- Migración `prestamos/0001_initial`; 16 tests → suite **202**.
- **Fix detectado en validación**: `test_tecnico_puede_crear` falló porque `setUp` ya tenía un préstamo vigente sobre el mismo activo → usar un activo nuevo en el test. (Demuestra que la validación anti-duplicado funciona.)

---

## 8. Estrategia de Pruebas (suite completa 202/202 OK)

Evolución del conteo durante el sprint:

| Hito | Tests |
|------|-------|
| Inicio (Fases 1-2) | +81 tests nuevos (core, usuarios, mantenimiento, documentos, passwords, reports, yule) |
| Fase 3 (mantenimiento) | +12 → **153** |
| Fase 4 — cobertura (extra) | → **153** totales con Fase 3; **167** al sumar soporte (14) |
| Fase 5 (licencias) | +19 → **186** |
| Fase 6 (préstamos) | +16 → **202** |

Patrones técnicos clave del sprint:

- **WeasyPrint sin GTK**: todos los PDF (actas, etiquetas, reportes, licencias) probados con **mock de `sys.modules`** (`patch.dict("sys.modules", {"weasyprint": _FakeWeasyprint})`) — patrón Fase 2. En runtime se importa tan solo la pila WeasyPrint.
- **Migraciones sin BD rota**: antes de reconstruir la BD dev, las nuevas migraciones se generaban/validaban en una BD SQLite temporal vía `sysadmin.settings._tmp_scratch` (archivo `_tmp_scratch.py` fuera de git), verificando que el **grafo completo de migraciones** aplicara en limpio, y se eliminaban los temporales al final. **Ya no es necesario** tras la reconstrucción (§9) → settings dev/base listos.
- **Tests por responsabilidad**: login_required, CRUD, permisos por rol (lectura no escribe), validaciones de dominio (estados, duplicados), filtros, exports.

---

## 9. Corrección de Infraestructura Local (BD dev + drift) ✅

**Detectado al validar el cierre del sprint:**

- `backend/db.sqlite3` (dev) tenía **historial de migraciones inconsistente pre-existente**: faltaban `accounts.0001/0002` (no existía la tabla `accounts_customuser`, necesaria para `AUTH_USER_MODEL = accounts.CustomUser`, evidenciando apps creadas por syncdb en el pasado), y **sin datos de negocio** (0 usuarios, 0 activos, 0 órdenes).

**Acción (preservando seguridad):**
1. Backup de la BD antigua → `backend/db.sqlite3.legacy_20260910`.
2. **Reconstrucción desde cero**: `manage.py migrate` aplica **las 42 migraciones** de las 16 apps en orden correcto.
3. Seed mínimo dev: superuser `admin` (rol `superadmin`) y singleton `ConfiguracionSistema`. Credencial dev generada localmente y **no versionada** (fuera del repo).

**Drift resuelto** (reportaba `makemigrations --check`):
- `yule/0002_rename_...` — renombres de 4 índices de `EquipoOCS` (migración **funcionalmente no-op**, refleja el estado de la app instalada).
- `administracion/0002_alter_registroauditoria_modulo` — choices de `modulo` actualizados con los módulos Fases 4-6 (derivación dinámica de `MODULOS`). En SQLite no-op; en Postgres solo ALTER sin pérdida.

**Verificación tras el fix:**
- `makemigrations --check --dry-run` → **No changes detected**
- `manage.py check` → 0 issues
- Suite completa → **202/202 OK**

---

## 10. Documentación

- **`README.md`** → **v1.8.1**: estado "Etapas 0-8 + Fases 1-6 (plan completo)", tabla de módulos con `licencias` y `prestamos` nuevos, changelog v1.8.0/v1.8.1, tareas pendientes actualizadas.
- **`FASES.md`** (nuevo): registro del plan por fases (objetivo/alcance/archivos/migraciones/tests/notas; Fases 1-6 + Fase 4 EXTRA renombrada como detour).
- **`SYSADMIN_HANDOFF.md`**: tabla de estado con las 6 fases, TAREAS CRÍTICAS PENDIENTES actualizadas (drift y BD dev resueltas), changelog de cada fase y de la corrección.
- **`AGENTS.md`**: reitera "no commits salvo pedido explícito".

---

## 11. Verificación Final del Sprint

| Comprobación | Resultado |
|--------------|-----------|
| Suite de tests completa | **202/202 OK** |
| `manage.py check` | **0 issues** |
| `makemigrations --check` | **No changes detected** |
| `migrate` (BD dev reconstruida) | **42/42 OK** |
| Apps nuevas | accounts/administracion/notificaciones/soporte/licencias/prestamos registradas en INSTALLED_APPS + URLs |

---

## 12. Pendientes de Deploy en Servidor (requieren acceso al contenedor)

1. **Reconstruir imagen Docker** (dependencia nueva `qrcode==8.2`) y recrear contenedores.
2. Ejecutar `migrate` — incluye **4 migraciones nuevas por fase** (soporte, licencias, prestamos, mantenimiento 0002/0003, administracion 0002, yule 0002, passwords 0002/0003 ya existentes).
3. `collectstatic --noinput` y reiniciar `django`.
4. Validación **manual obligatoria** (no automatizable):
   - Reportes configurables Excel/PDF desde `/inventario/exportar/opciones/`.
   - Importación masiva (vista previa, badges, race-guard de duplicados).
   - Etiquetas QR individual/masiva (verificar render en navegador y PDF).
   - Flujo completo: reportar falla → ticket de soporte → mantenimiento vinculado.
   - Licencias (crear/exportar) y Préstamos (crear/devolver, vencidos).
5. Configurar `SECRET_KEY` y `PASSWORDS_ENCRYPTION_KEY` reales en `.env` (hoy se generan temporales si faltan).

---

## 13. Estado de Git y Commits Recomendados

- **Ningún commit realizado** (regla del proyecto). Working tree con **55 archivos**: 27 modificados + 28 nuevos/untracked (apps completas `administracion/`, `soporte/`, `licencias/`, `prestamos/`, `notificaciones/`, `accounts/permisos.py` + templatetags, migraciones de cada fase, tests).
- `db.sqlite3` y `_tmp_scratch` (ya eliminado) no versionados.
- `db.sqlite3.legacy_20260910` (backup BD antigua) queda **untracked**; decidir si versionarlo o borrarlo. Recommend: no versionar (dato sensible), eliminar tras confirmar estabilidad.

**Agrupación sugerida de commits** (decisión del arquitecto):
1. `feat(security): roles y permisos @requiere_permiso + auditoría + ConfiguracionSistema` (Fase 1)
2. `feat(inventario): etiquetas QR individuales y masivas` (Fase 2)
3. `feat(mantenimiento): notificaciones, checklist, criticidad, calendario y portal de reporte` (Fase 3)
4. `feat(soporte): helpdesk de tickets con asignación, estados y escalado a mantenimiento` (Fase 4)
5. `feat(licencias): inventario de licencias con vencimientos y exports` (Fase 5)
6. `feat(prestamos): préstamos de equipos con devolución y estados` (Fase 6)
7. `test: cobertura total 202/202` (incluye tests de todas las apps)
8. `fix(migraciones): rebuild BD dev + yule/0002 + administracion/0002` (o integraciones de migraciones)
9. `docs: README v1.8.1 + FASES.md + SYSADMIN_HANDOFF.md`

---

## 14. Riesgos y Deuda Técnica

- **WeasyPrint en servidor**: requiere las librerías del sistema (GTK/Pango) para los PDFs reales; el mock solo cubre tests. Validar en contenedor.
- **`roles` en choices**: agregar un rol futuro requiere migración en `CustomUser.rol`.
- **Filtro por estado efectivo en Python**: rendimiento aceptable para volumen interno, pero si crece el inventario (licencias/préstamos > miles) conviene pasarlo a ORM con campos derivados (e.g., `fecha_vencimiento__lte`).
- **`ConfiguracionSistema`**: singleton con `get_config()`, no hay endpoints de API, solo vistas HTML.
- **`requiere_permiso` sin fallback por `is_superuser`**: autoriza solo por `rol`. La migración `accounts/0002` asigna `superadmin` a superusuarios existentes al migrar, pero un superusuario **creado después** (e.g., `createsuperuser`) nace con `rol='tecnico'` (default del campo) y queda limitado en las vistas con `@requiere_permiso` hasta que se le asigne `superadmin`. Decidir: añadir bypass `is_superuser` en el decorador o sobreescribir `createsuperuser`.
- **BD de producción**: verificar que la BD real en servidor **no** tenga el historial inconsistente como la dev; el deploy debe correr las 42 migraciones en una BD limpia o ya consistente.
- **Contraseña dev `admin`**: solo local; en servidor usar credenciales reales y nunca registrarlas en el repo.

---

**Preparado por:** Asistente SysAdmin  
**Próxima sesión sugerida:** commitear los cambios (agrupación §13), desplegar en servidor (§12) y validar en producción el flujo end-to-end.