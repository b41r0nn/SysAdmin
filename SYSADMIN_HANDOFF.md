# SysAdmin · HANDOFF DOCUMENT
> Documento actualizado: 2026-09-25 · v1.10.0 + Fase 7 (seguridad) · 313 tests OK

---

## CHANGELOG DE PRODUCCIÓN

### 2026-09-25 · OCS Inventory NG en producción + fix de MEDIA_ROOT

**MEDIA_ROOT: volumen con nombre → bind mount (fix real).**
El primer deploy usaba `media_volume:/app/media` en `docker-compose.yml`.
Consecuencias: los archivos subidos por la web quedaban dentro de
`/var/lib/docker/volumes/`, invisibles desde el host, imposibles de respaldar,
y el `rsync` de despliegue los excluía (`backend/media/` en los excludes). Los
registros de `documentos_documento` existían en la BD pero "ver" fallaba porque
el archivo no estaba en disco. Además nginx servía `/media/` desde el mismo
volumen (`nginx.conf:40-42`), así que cambiar solo un servicio no bastaba.

Cambios aplicados:
- `docker-compose.yml`: `./backend/media:/app/media` en **django y nginx**; se
  eliminó la declaración del volumen `media_volume` (ya sin uso).
- `setup_server.sh`: crea `/opt/sysadmin/app/backend/media` con `chmod 777`
  antes de levantar (si no, Docker lo crea como root y el contenedor corre como
  uid 1000 → `Permission denied` al subir).
- `setup_server.sh` (`backup.sh`): la ruta de media era
  `/opt/sysadmin/media/` (inexistente) → corregida a
  `/opt/sysadmin/app/backend/media/`, y se agregó el `.env` al paquete
  (contiene `SECRET_KEY` y `PASSWORDS_ENCRYPTION_KEY`, sin los cuales el vault
  queda ilegible).

**Documentos: los 2 PDFs sí estaban en el server.** El dump de BD no
transporta archivos, y la búsqueda en la máquina local dio negativo (los 365
archivos de `backend/media/` local son casi todos de 0 KB, uploads de pruebas;
el volumen Docker `SysAdmin_media_volume` estaba vacío), lo que llevó a pensar
que los archivos se habían perdido. Corrección: **estaban en
`/opt/sysadmin/app/backend/media/documentos/2026/09/`** y no se veían desde el
contenedor por el bug del volumen con nombre, no por ausencia. Ahora con el bind
mount: `MANUAL_PARA_RESTAURAR_BASE_DE_DATOS.pdf` (453 458 B, PDF 1.7, 7 pág.) y
`Actualizacion_version_de_DMS.pdf` (425 403 B, PDF 1.7, 4 pág.) sirven **200** vía
nginx. No hay que volver a subirlos.

### 2026-09-25 · OCS Inventory NG 2.12.1 desplegado (puerto 8081)

- Puerto `:8081` (no 8080) porque el host tiene **80/443 ocupados por
  Hikvision**. Por eso el `ocsproxy` de OCS (que pide `80:80` y `443:443`)
  queda en `Restarting (1)` y se deja **detenido** a propósito; el acceso
  directo al server en 8081 lo reemplaza.
- La tabla de usuarios es **`operators`**, no `users`. `NEW_ACCESSLVL` debe ser
  `'sadmin'` (NULL → "NO HAY DEFINIDO NINGÚN NIVEL DE PERMISOS") y
  `PASSWORD_VERSION` debe ser `1` (con `2` se traba el primer ingreso).
- **Parche obligatorio** en `require/html_header.php:236`: bug de PHP 8 donde
  `array_search()` recibe `null` (a diferencia de la línea 92 del mismo archivo,
  que sí valida `is_array()`). Sin el parche la consola muestra solo el logo.
- API JSON: `/ocsapi/v1/` responde 404 (normal, no existe) pero
  `/ocsapi/v1/computers` responde 200. `null` en el cuerpo = sin equipos
  inventariados, no es error.
- Agente Windows publicado en `http://192.168.1.250:8081/download/OcsInventoryAgent.exe`.
  El repo correcto es `OCSInventory-NG/WindowsAgent` (no `OCSInventory-Agent`).
  El server no puede descargar de GitHub (proxy: raíz 200, sub-rutas 404), hay
  que bajar en Windows y hacer `scp`.
- SOAP no funciona (`Cannot find XML::Entities`): `libxml-entities-perl` no
  existe en Ubuntu 22.04. La web y la API JSON sí.

Detalle completo en `OCS_INVENTORY_SETUP.md` (reescrito) y `AGENT_RUNBOOK.md`.

---

## ESTADO ACTUAL (2026-06-05)

| Etapa | Módulo | Estado |
|-------|--------|--------|
| 0 | Fundación Docker+Django+Nginx | ✅ COMPLETA |
| 1 | accounts — Login/auth/sesión | ✅ COMPLETA |
| 2 | usuarios — BD personas | ✅ COMPLETA |
| 3 | inventario — Activos | ✅ COMPLETA · import masiva + plantillas v1.1.0+ · etiquetas QR (Fase 2) |
| 4 | reports — Reportes | ✅ COMPLETA · export configurables Excel/PDF post-v1.1.0 |
| 5 | mantenimiento — Órdenes | ✅ COMPLETA |
| 6 | passwords — Vault | ✅ COMPLETA |
| 7B | yule — Sincronización OCS | ✅ COMPLETA |
| 8 | documentos — Repositorio documental | ✅ COMPLETA v1.1.0 |
| Fase 1 | administracion — Roles + permisos + auditoría | ✅ COMPLETA 2026-09-10 |
| Fase 2 | inventario — Etiquetas QR | ✅ COMPLETA 2026-09-10 |
| Fase 3 | notificaciones + checklist + criticidad + calendario + reportar | ✅ COMPLETA 2026-09-10 |
| Fase 4 EXTRA | Tests de cobertura (todas las apps) | ✅ COMPLETA 2026-09-10 · 153 tests |
| Fase 4 (plan) | Helpdesk / Tickets (app `soporte`) | ✅ COMPLETA 2026-09-10 · 167 tests |
| Fase 5 | Licencias de software (app `licencias`) | ✅ COMPLETA 2026-09-10 · 186 tests |
| Fase 6 | Préstamos de equipos (app `prestamos`) | ✅ COMPLETA 2026-09-10 · 202 tests |
| v1.9.0 | Detector vencimiento de licencias en notificaciones | ✅ COMPLETA 2026-09-10 · `c9f18ac` |
| v1.9.0 | Gestión de cuentas de usuario `/administracion/cuentas/` | ✅ COMPLETA 2026-09-10 · `36d58bb` |
| — | Commits del sprint §13 (9) ejecutados | ✅ COMPLETA 2026-09-10 · `1565d08`→`5094cba` |
| Fase 7 | Seguridad del login (django-axes) + auditoría de fallos | ✅ COMPLETA 2026-09-24 · 313 tests |
| Fase 7 | HTTPS interno LAN (nginx + cert autofirmado) | ✅ COMPLETA 2026-09-24 · pendiente validar en Docker |

---

## 🔴 TAREAS CRÍTICAS PENDIENTES

1. **Deploy v1.1.0 + Fases 1-7 + v1.9.0 en servidor**
   - Ejecutar `migrate` para aplicar migraciones pendientes de todas las etapas/fases (incluye `licencias/0002` y `notificaciones/0002` de las features de cierre)
   - Reconstruir imagen Docker (dependencia nueva `qrcode==8.2` y `django-axes==8.3.1`)
   - `collectstatic --noinput` y reiniciar contenedor Django
   - Configurar `SECRET_KEY` y `PASSWORDS_ENCRYPTION_KEY` reales en `.env`
   - Verificar módulo Administración (auditoría + configuración + **Cuentas**), sidebar por rol, etiquetas QR y detector de licencias en la campana de notificaciones

2. **Validar HTTPS (Fase 7) en el servidor**: el acceso ahora es `https://192.168.1.250:6060` (cert autofirmado `nginx/certs/`); `http://...:6061` debe redirigir 301 a HTTPS. Confirmar con `docker compose up -d --build` que https carga sin 500 (warning del cert autofirmado es esperable en LAN). Recordar renovar el cert (~dic 2028).

3. **Decidir manejo de `admin.py`**: la mayoría de apps registran modelos sin restricciones (borrado/CRUD completo vía /admin/). Solo `administracion` (auditoría) y `yule/SincronizacionLog` son read-only. Decidir `unregister` vs `has_delete_permission`.

4. **Usuarios legados**: cuentas creadas antes de la migración de roles o vía `createsuperuser` pueden tener `rol != superadmin` con `is_staff=True` → aún entran a /admin/. Validador manual.

5. **Tests automatizados activos**: 313/313 tests OK (todas las apps — Fases 1-7). Ejecutar con `manage.py test`.

6. ~~drift de migraciones~~ → **RESUELTO 2026-09-10**: se generaron y aplicaron `yule/0002` (renombres de índices) y `administracion/0002` (choices de `modulo` con módulos nuevos). `makemigrations --check` → *No changes detected*.

7. **BD local dev reconstruida el 2026-09-10**: el `db.sqlite3` previo tenía historial de migraciones inconsistente (sin `accounts_customuser` ni datos de negocio). Se reconstruyó de cero: `migrate` (42 migraciones), superuser `admin` (rol `superadmin`) y singleton `ConfiguracionSistema`. Credencial dev generada localmente, **no versionada** (no registrar en commits ni en `.env.example`).

8. **Cambios de seguridad sin commitear (Fase 7)**: el endurecimiento del login (django-axes, forms, signals, headers, cookies, HTTPS) quedó en el working tree para revisión del arquitecto. Ver detalle en `docs/sesiones/SESION_2026-09-24_RESUMEN.md`.

---

## ✅ FASE 1 — Módulo de Administración (roles + permisos + auditoría) [Completada 2026-09-10]

- Matriz de permisos `accounts/permisos.py` (`PERMISOS_POR_ROL`) + decorador `@requiere_permiso(módulo, nivel)` en TODAS las vistas (usuarios, inventario, reports, mantenimiento, passwords, documentos, yule→inventario).
- Roles en `CustomUser.rol` (superadmin/admin/tecnico/lectura) con migración + data migration.
- Nueva app **`administracion`**: `RegistroAuditoria` (con signals login/logout), `ConfiguracionSistema` (singleton, usado en etiquetas QR y actas), vistas `auditoria/` y `configuracion/`, template tag `tiene_permiso` + sidebar condicional.
- WeasyPrint movido a imports locales (desbloquea `makemigrations`/`check`/`test` local sin GTK).
- Tests: `accounts/tests.py`, `administracion/tests.py`.

## ✅ FASE 2 — Etiquetas QR para activos [Completada 2026-09-10]

- Dependencia nueva: `qrcode==8.2` (PNG puro, sin GTK). QR cifra la URL absoluta de la ficha del activo (`inventario/detalle`).
- Endpoints nuevos en `inventario` (todos `@requiere_permiso("inventario", "lectura")`):
  - `GET /inventario/<pk>/qr/` → PNG del código QR (usado en la ficha del activo).
  - `GET /inventario/<pk>/etiqueta/` → PDF de etiqueta individual (50×30 mm).
  - `GET/POST /inventario/etiquetas/` → página de selección masiva → PDF con hasta 8 etiquetas por hoja A4.
- Plantillas: `inventario/etiqueta_pdf.html` (standalone WeasyPrint, patrón `acta_pdf.html`) y `inventario/etiquetas_seleccion.html` (web con checkboxes, selector "todos" y contador).
- Integración: botón en `lista.html`, icono QR por fila en `partials/tabla.html`, vista previa del QR + botón en `detalle.html`.
- La cabecera de la etiqueta usa `ConfiguracionSistema.nombre_empresa` y NIT de la Fase 1.
- Tests: `inventario/tests.py` (10 nuevos: permisos, PNG válido, PDF mockeado sin WeasyPrint real, selección masiva, render de plantilla con QR real).
## ✅ FASE 3 — Sistema de notificaciones por usuario [Completada 2026-09-10]

- Nueva app **`notificaciones`**: modelo `Notificacion`, detectores perezosos, vistas de bandeja y marcar leídas.
- **Detectores** (corren al consultar bandeja/campana, idempotentes via `get_or_create`):
  - `garantia` — activos con garantía vencida (≤ hoy) o por vencer (≤ 30 días). Excluye dados de baja.
  - `mantenimiento` — `PlanMantenimiento.proxima_ejecucion` atrasada o próxima (7 días). Solo `estado="activo"`.
  - `acta` — `ActaAsignacion` sin firma escaneada.
  - `ocs` — `EquipoOCS` sin `activo_local` vinculado.
- **Permisos por rol**: cada detector solo corre si el rol tiene acceso al módulo relevante (`_puede_ver` usa `PERMISOS_POR_ROL`).
- **Fix aplicado**: `_detectar_actas` usa `Q(escaneado_firmado="") | Q(escaneado_firmado__isnull=True)` (FileField almacena `""`, no NULL).
- **Campana HTMX** en sidebar: badge de no leídas cargado al cargar la página (`hx-trigger="load"`).
- **Vistas**: `lista_notificaciones`, `cantidad`, `marcar_leida`, `marcar_todas_leidas` — todas `@login_required`, sin `@requiere_permiso`.
- Tests: `notificaciones/tests.py` (31 tests — modelo, detectores, idempotencia, vistas, permisos).
- Suite completa: 61/61 tests OK, `manage.py check` 0 issues.

## ✅ FASE 4 — Tests de cobertura [Completada 2026-09-10]

- Tests para las 7 apps sin cobertura previa (81 tests nuevos):
  - `core/tests.py` (3): dashboard login/status/context.
  - `usuarios/tests.py` (12): CRUD + plantilla Excel + permisos.
  - `mantenimiento/tests.py` (16): planes, órdenes (cerrar/ya cerrada), repuestos + permisos.
  - `documentos/tests.py` (11): CRUD documentos/categorías + protección categoría + permisos.
  - `passwords/tests.py` (17): vaults, credenciales con cifrado Fernet, acceso con código Argon2, export, logs + permisos.
  - `reports/tests.py` (12): index, 5 Excel, 2 PDF (WeasyPrint mockeado vía `patch.dict("sys.modules")`) + permisos.
  - `yule/tests.py` (10): models + vistas (reemplaza placeholder).
- **Bug real corregido**: `passwords/views.py` — `_log_action` corría después de `delete()` (FK apuntaba a objeto borrado → `ValueError: save() prohibited`). Ahora el log se escribe antes del borrado (`vault_eliminar`, `credencial_eliminar`).
- Detalle: en ModelForm, un campo con `blank=False` y `default` sigue siendo `required`; los tests ahora envían `estado`/`orden` donde corresponde.
- Suite completa: **142/142 tests OK**, `manage.py check` 0 issues.

## ✅ FASE 7 — Seguridad del login + HTTPS interno [Completada 2026-09-24]

Endurecimiento del login siguiendo instrucciones del arquitecto (7 tareas). Los cambios quedaron **en el working tree, SIN commitear** (revisión del arquitecto).

### 1. Rate limit / lockout — django-axes 8.3.1
- `django-axes==8.3.1` en `requirements.txt` (raíz). Migraciones de axes aplicadas.
- Settings (`sysadmin/settings/base.py`):
  - `INSTALLED_APPS += "axes"`; `MIDDLEWARE` reemplaza `accounts.middleware.LoginRateLimitMiddleware` (eliminado) por `axes.middleware.AxesMiddleware`.
  - `AUTHENTICATION_BACKENDS = ["axes.backends.AxesStandaloneBackend", "django.contrib.auth.backends.ModelBackend"]`
  - `AXES_FAILURE_LIMIT = 5`, `AXES_COOLOFF_TIME = 1` (hora), `AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]`, `AXES_RESET_ON_SUCCESS = True`
  - Mensajes de lockout genéricos (`AXES_IP_COOLOFF_MESSAGE`, `AXES_COOLOFF_MESSAGE`, `AXES_LOCKOUT_MESSAGE`).
- Runtime real verificado: 5 intentos fallidos → HTTP **429** (bloqueo); login exitoso → `AccessAttempt` reseteado a 0.

### 2. Mensajes de error genéricos — `accounts/forms.py` (nuevo)
- `SysAdminAuthenticationForm(AuthenticationForm)`: `invalid_login` = "Usuario o contraseña incorrectos." (no revela si el usuario existe); `inactive` = "Esta cuenta está inactiva. Contacte al administrador."
- Conectado vía `authentication_form=` en `accounts/urls.py`.

### 3. Auditoría de intentos fallidos — `accounts/signals.py` (nuevo)
- `user_login_failed` → `registrar_auditoria(modulo="auth", accion="login_fallido", detalle="…usuario '<username>'.")`.
- `axes.signals.user_locked_out` → `accion="cuenta_bloqueada"` (usuario + IP).
- IP: soporta `HTTP_X_FORWARDED_FOR` (primer hop) detrás de nginx.
- Cargado en `accounts/apps.py::ready()`.

### 4. Password validators
- `AUTH_PASSWORD_VALIDATORS`: `MinimumLengthValidator(min_length=10)`, `UserAttributeSimilarityValidator`, `CommonPasswordValidator`, `NumericPasswordValidator`.

### 5. Headers de seguridad
- `SECURE_CONTENT_TYPE_NOSNIFF = True`, `X_FRAME_OPTIONS = "DENY"`, `SECURE_REFERRER_POLICY = "same-origin"` (verificados en runtime: `nosniff`/`DENY`/`same-origin`).

### 6. Cookies de sesión
- `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`, `SESSION_COOKIE_AGE = 28800` (8 h), `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`.
- `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`/`SECURE_SSL_REDIRECT` siguen configurables por env (default `False`).

### 7. HTTPS interno LAN
- Cert autofirmado `nginx/certs/server.crt` + `server.key` (CN=192.168.1.250, 825 días: 24-sep-2026 → 27-dic-2028), generado con OpenSSL de Git (Windows).
- `nginx/nginx.conf`: puerto 80 → `return 301 https://$host$request_uri`; puerto 443 ssl con certificates + headers de seguridad; proxy a `django:8000` con `X-Forwarded-Proto`.
- `docker-compose.yml`: puertos nginx `6060:443` (HTTPS) + `6061:80` (HTTP → redirect); volumen `./nginx/certs:/etc/nginx/certs:ro`.
- CSRF trusted origins incluyen `https://localhost:6060` / `https://192.168.1.250:6060` (defaults y `.env`).

### Tests
- `accounts/tests.py`: clase `LoginSeguridadTests` (~11 tests: mensaje genérico, no revela existencia, 5 fallos en BD, 429, auditoría, reset por éxito, cookies, headers, config axes, validators).
- `administracion/tests.py` y `soporte/tests.py`: migrados a `force_login` (axes exige request en `authenticate`).
- Suite completa: **313/313 OK** (302 + 11) · `manage.py check` 0 issues · `makemigrations --check` sin cambios.

### Notas
- **Pendiente de validar con Docker**: https:// carga sin 500 y http:// → 301 (Docker Desktop no corriendo en la máquina local).
- Credenciales de test usadas en validación (`validacion_seg`) y registros `auth/login_fallido` en la `db.sqlite3` de dev (no versionada).

## CRONOGRAMA ETAPAS 6 Y 7 (PROPUESTA vs REALIDAD)

### ✅ ETAPA 6 — passwords (Completada)
- 6A: Base técnica (Vault, Credencial, migraciones)
- 6B: CRUD + UI (Forms, vistas, templates)
- 6C: Seguridad (cifrado, argon2)
- 6D: Export + Logs (CSV/Excel, auditoría)

**Status**: COMPLETA · Modelos, vistas, templates, admin

---

### ✅ ETAPA 7B — yule (Sincronización) [Completada 2026-06-05]

#### Implementación

**Modelos (models.py - 140 líneas)**
- `EquipoOCS`: Almacena equipos de OCS con relación FK a Inventario local
- `SincronizacionLog`: Auditoría de cada sincronización (estado, estadísticas, duración)
- `ConfiguracionYule`: Configuración global (frecuencia, auto-sync para futuro Celery)

**Cliente OCS (client.py - 180 líneas)**
```python
class OCSClient:
    - is_configured()        # Verifica credenciales
    - request()             # HTTP con retry logic (3 intentos, exponential backoff)
    - get_computers()       # Obtiene lista de OCS
    - test_connection()     # Valida conectividad
```

Excepciones:
- `OCSClientException` (base)
- `OCSAuthError` (401, 403)
- `OCSConnectionError` (timeout, conexión)

**Sincronización (sync.py - 250 líneas)**
```python
sincronizar_equipos_ocs(usuario, force)
    # Valida frecuencia mínima
    # Conecta OCS y obtiene equipos
    # Crea/actualiza EquipoOCS en BD
    # Marca desaparecidos
    # Genera SincronizacionLog
    # Retorna (log, mensaje)

verificar_equipos_sin_match()          # Lista equipos no vinculados
buscar_posibles_matches(equipo)        # Busca por serial/MAC/hostname
```

**Vistas (views.py - 200 líneas)**
1. `index` — Dashboard con estadísticas
2. `equipos_lista` — Paginada (25), filtros, búsqueda HTMX
3. `equipo_detalle` — Info completa + posibles matches
4. `sincronizar` — POST para sync manual (admin only)
5. `historial_sincronizaciones` — Auditoría con filtros
6. `equipos_sin_match` — Sin vincular a inventario
7. `test_conexion_ocs` — API JSON

**Admin (admin.py - 250 líneas)**
- `EquipoOCSAdmin`: List display con badges, filters, search, fieldsets
- `SincronizacionLogAdmin`: Read-only, estadísticas formateadas
- `ConfiguracionYuleAdmin`: Editable, auto-asigna user

**Management Command (sync_ocs.py)**
```bash
python manage.py sync_ocs           # Normal
python manage.py sync_ocs --force   # Fuerza sin validar frecuencia
python manage.py sync_ocs --user=admin
```

**Templates (5 HTML - ~800 líneas)**
- `index.html`: Dashboard mejorado
- `equipos_lista.html`: Listado paginado
- `equipo_detalle.html`: Información completa
- `historial_sincronizaciones.html`: Auditoría
- `equipos_sin_match.html`: Sin vincular

**Migrations (0001_initial.py)**
- 3 modelos + 4 índices (id_ocs, hostname, mac, activo_local)

**URLs**
```python
/yule/                      # Dashboard
/yule/equipos/              # Lista paginada
/yule/equipos/<id>/         # Detalle
/yule/equipos/sin-match/    # Sin vincular
/yule/sincronizar/          # POST sync
/yule/historial/            # Auditoría
/yule/api/test-conexion/    # API JSON
```

#### Estadísticas Yule 7B

| Métrica | Valor |
|---------|-------|
| Líneas de código | ~1900 |
| Modelos Django | 3 |
| Vistas | 7 |
| Templates | 5 |
| Admin classes | 3 |
| Management commands | 1 |
| Migrations | 1 |

#### Configuración `.env`

```ini
OCS_BASE_URL=https://ocs.tu-empresa.local/ocsapi/v1
OCS_USER=usuario_ocs
OCS_TOKEN=token_ocs_aqui
OCS_VERIFY_SSL=True
```

> **Instalación del servidor OCS:** ver `OCS_INVENTORY_SETUP.md` — runbook completo de instalación en 192.168.1.250 y conexión con Yule.

#### Próximos Pasos (7C-7D)

- [ ] Alertas por equipos nuevos/sin match
- [ ] Sincronización automática con Celery
- [ ] Reporte de comparación OCS vs Inventario
- [ ] Dashboard mejorado con métricas OCS

**Status**: LISTO PARA TESTING EN SERVIDOR

---

### CRONOGRAMA ORIGINAL (Referencia)


## STACK TÉCNICO

- Backend: Django 4.2 + Python 3.11
- DB: PostgreSQL 15
- Frontend: Bootstrap 5.3 + Django Templates + HTMX
- Fuentes: Sora (UI) + JetBrains Mono (datos técnicos)
- Reportes PDF: WeasyPrint · Excel: openpyxl
- Contenedores: Docker Compose · Proxy: Nginx
- Servidor: Ubuntu Server 22.04 · IP: 192.168.1.250 · Solo LAN
- 1 SuperAdmin únicamente

---

## RUTA LOCAL (PC Windows)

```
C:\Users\Sistemas\OneDrive - EMPRESA\Escritorio\Vscode\SysAdmin\
```

---

## DESIGN SYSTEM (variables CSS — NO cambiar)

```css
--sa-primary:       #1a56db
--sa-primary-dark:  #1341b0
--sa-primary-light: #e8effe
--sa-accent:        #0ea5e9
--sa-sidebar-bg:    #0f172a
--sa-sidebar-w:     260px
--sa-sidebar-w-col: 68px
--sa-topbar-h:      60px
--sa-bg:            #f1f5f9
--sa-card-bg:       #ffffff
--sa-font:          'Sora', sans-serif
--sa-font-mono:     'JetBrains Mono', monospace
--sa-radius:        10px
--sa-radius-lg:     16px
```

---

## ESTRUCTURA DE ARCHIVOS (completa a la fecha)

```
SysAdmin/
├── docker-compose.yml                ← puertos 6060:443 (https) + 6061:80 (http→https)
├── .env
├── .gitignore
├── README.md                        ← DOCUMENTACIÓN CON YULE 7B
├── SYSADMIN_HANDOFF.md              ← ESTE DOCUMENTO
├── CHECKLIST_DEPLOY.md              ← runbook de despliegue en producción
├── FASES.md                         ← registro del plan por fases
├── setup_server.sh
├── docs/
│   └── sesiones/                    ← bitácora histórica de sesiones (resúmenes)
├── nginx/
│   ├── Dockerfile
│   ├── nginx.conf                   ← 443 ssl + redirect 301 desde 80
│   └── certs/                       ← FASE 7: server.crt + server.key (autofirmado)
└── backend/
    ├── Dockerfile
    ├── entrypoint.sh
    ├── manage.py
    ├── requirements.txt             ← copia histórica (puede desalinearse)
    ├── static/
    │   ├── css/sysadmin.css
    │   ├── js/sysadmin.js
    │   └── img/
    ├── templates/
    │   └── base.html
    ├── sysadmin/
    │   ├── settings/
    │   │   ├── __init__.py
    │   │   └── base.py
    │   ├── urls.py
    │   └── wsgi.py
    ├── accounts/                ← ETAPA 0-1 COMPLETA · FASE 7: forms.py (login genérico) + signals.py (auditoría de fallos)
    ├── core/                    ← ETAPA 0 COMPLETA
    ├── usuarios/                ← ETAPA 2 COMPLETA
    ├── inventario/              ← ETAPA 3 COMPLETA
    ├── reports/                 ← ETAPA 4 COMPLETA
    ├── mantenimiento/           ← ETAPA 5 COMPLETA
    ├── passwords/               ← ETAPA 6 COMPLETA
    ├── yule/                    ← ETAPA 7B COMPLETA
    ├── documentos/              ← ETAPA 8 COMPLETA v1.1.0
    ├── administracion/          ← FASE 1: auditoría + configuración + roles
    └── notificaciones/          ← FASE 3: notificaciones por usuario

    └── yule/                    ← ETAPA 7B COMPLETA
        ├── __init__.py
        ├── admin.py             ← Admin customizado con badges
        ├── apps.py
        ├── client.py            ← Cliente OCS con retry logic
        ├── models.py            ← 3 modelos (Equipo, Log, Config)
        ├── sync.py              ← Lógica de sincronización
        ├── views.py             ← 7 vistas
        ├── urls.py              ← 6 rutas
        ├── tests.py             ← Tests (TODO)
        ├── migrations/
        │   ├── __init__.py
        │   └── 0001_initial.py  ← Migraciones iniciales
        ├── management/
        │   ├── __init__.py
        │   └── commands/
        │       ├── __init__.py
        │       └── sync_ocs.py  ← Command para sincronizar
        └── templates/yule/
            ├── index.html                           ← Dashboard
            ├── equipos_lista.html                   ← Lista paginada
            ├── equipo_detalle.html                  ← Detalle
            ├── historial_sincronizaciones.html      ← Auditoría
            └── equipos_sin_match.html               ← Sin vincular
```

---

## APPS DJANGO (sysadmin/settings/base.py)

```python
INSTALLED_APPS = [
    # django defaults...
    "accounts",
    "core",
    "usuarios",
    "inventario",
    "reports",
    "mantenimiento",
    "passwords",
    "yule",              # ← ETAPA 7B: Sincronización OCS
    "documentos",        # ← ETAPA 8: Repositorio documental v1.1.0
    "administracion",    # ← FASE 1: Auditoría + configuración + roles
    "notificaciones",    # ← FASE 3: Notificaciones por usuario
    "axes",              # ← FASE 7: Rate limit / lockout del login
]
```

---

## MODELO usuarios.Usuario (referencia para FK en inventario)

```python
class Usuario(models.Model):
    nombre_completo     = CharField(max_length=200)
    documento_identidad = CharField(max_length=50, unique=True)
    cargo               = CharField(max_length=150)
    area                = CharField(max_length=150)
    correo              = EmailField()
    telefono            = CharField(max_length=50, blank=True)
    estado              = CharField(choices=[("activo","Activo"),("inactivo","Inactivo")], default="activo")
    foto                = ImageField(upload_to="usuarios/fotos/", blank=True, null=True)
    fecha_creacion      = DateTimeField(auto_now_add=True)
```

---

## ETAPA 3 — INVENTARIO: PLAN DE FRAGMENTACIÓN

El módulo inventario es el más grande. Se divide en **6 sub-etapas** independientes.
Cada sub-etapa cabe en un chat sin problemas de tokens.

```
3A → Models + Migration          ✅ COMPLETA
3B → Forms + Views CRUD          ✅ COMPLETA (incluye CRUD CatalogoModelo)
3C → Views movimientos + acta    ✅ COMPLETA (vistas + URLs wired)
3D → Templates lista + detalle   ✅ COMPLETA (lista + tabla partial + detalle + catalogo_lista)
3E → Templates form + acta PDF   ✅ COMPLETA (form.html + asignacion_form.html + acta_pdf.html)
3F → Patches + integración       ✅ COMPLETA · integrada en repo (deploy vía Docker; patches obsoletos eliminados)
```

### SUB-ETAPA 3A — Models + Migration

**Archivos a crear:**
```
backend/inventario/__init__.py
backend/inventario/apps.py
backend/inventario/models.py        ← PRINCIPAL
backend/inventario/admin.py
backend/inventario/migrations/__init__.py
backend/inventario/migrations/0001_initial.py
```

**Modelos requeridos:**

`CatalogoModelo` — plantillas para autocompletar al registrar
- tipo_dispositivo, marca, modelo, especificaciones_json

`Activo` — modelo principal (single table, campos nullable por tipo)
- Campos comunes: tipo_dispositivo (choices), marca, modelo, serial (único), estado
  (activo/en_mantenimiento/dado_de_baja/en_reparacion), ubicacion_fisica,
  fecha_compra, proveedor, valor_compra, garantia_fabrica_meses,
  garantia_extendida (bool), anios_garantia_extendida, foto_activo,
  observaciones, fecha_creacion (auto), fecha_actualizacion (auto)
- Campos Celular: imei (único, null), almacenamiento, ram_celular, procesador_celular,
  tipo_disco_celular, cuenta_correo_dispositivo, numero_linea, operador
- Campos Escritorio/Portátil: disco_capacidad, tipo_disco, ram, procesador,
  sistema_operativo, licencia_so, usuario_red, usuario_admin_local, ip_equipo, mac_equipo
- Campos Teléfono Fijo: extension, puerto_jack, linea_asignada
- Campos Monitor: pulgadas, resolucion, tipo_panel, conectores
- Properties calculadas: en_garantia (bool), fecha_vencimiento_garantia

`Asignacion` — registro de asignación activo↔usuario
- activo (FK Activo), usuario (FK usuarios.Usuario), fecha_asignacion,
  fecha_devolucion (null), observaciones, activa (bool, default True)

`Movimiento` — historial de ingresos/egresos/traslados/devoluciones
- activo (FK Activo), tipo (choices: ingreso/egreso/traslado/devolucion/baja),
  fecha, descripcion, realizado_por (CharField), usuario_destino (FK null)

`ActaAsignacion` — vincula asignación con PDF firmado
- asignacion (OneToOne), fecha_generacion (auto), pdf_generado (FileField),
  escaneado_firmado (FileField, null), observaciones

**Tipos de dispositivo (choices):**
```python
TIPOS = [
    ("celular", "Celular"),
    ("escritorio", "Equipo Escritorio"),
    ("portatil", "Portátil"),
    ("telefono_fijo", "Teléfono Fijo"),
    ("monitor", "Monitor"),
]
```

**Estado Activo (choices):**
```python
ESTADOS = [
    ("disponible", "Disponible"),
    ("asignado", "Asignado"),
    ("en_mantenimiento", "En mantenimiento"),
    ("en_reparacion", "En reparación"),
    ("dado_de_baja", "Dado de baja"),
]
```

---

### SUB-ETAPA 3B — Forms + Views CRUD activos

**Archivos a crear:**
```
backend/inventario/forms.py
backend/inventario/views.py         ← solo CRUD activos (lista/detalle/crear/editar)
backend/inventario/urls.py
```

**Vistas:**
- `lista_activos(request)` → filtros: tipo, estado, q (nombre/serial/marca) + HTMX partial
- `detalle_activo(request, pk)` → ficha completa + historial movimientos + asignación actual
- `crear_activo(request)` → form dinámico por tipo
- `editar_activo(request, pk)`
- `toggle_baja_activo(request, pk)` → nunca eliminar, solo cambiar estado a dado_de_baja

**Forms:**
- `ActivoForm` — ModelForm con widgets Bootstrap; mostrar/ocultar campos por tipo (JS en 3E)
- `CatalogoModeloForm` — para CRUD del catálogo

**URLs namespace:** `inventario`
```python
urlpatterns = [
    path("", lista_activos, name="lista"),
    path("nuevo/", crear_activo, name="crear"),
    path("<int:pk>/", detalle_activo, name="detalle"),
    path("<int:pk>/editar/", editar_activo, name="editar"),
    path("<int:pk>/baja/", toggle_baja_activo, name="baja"),
    # movimientos — se agregan en 3C
]
```

---

### SUB-ETAPA 3C — Views movimientos + acta PDF

**Archivos a modificar/ampliar:**
```
backend/inventario/views.py         ← agregar vistas de movimientos
backend/inventario/urls.py          ← agregar URLs movimientos
```

**Vistas nuevas:**
- `asignar_activo(request, pk)` → crea Asignacion + Movimiento(ingreso) + ActaAsignacion
- `devolver_activo(request, pk)` → cierra Asignacion activa, crea Movimiento(devolucion)
- `trasladar_activo(request, pk)` → devuelve + reasigna, crea Movimiento(traslado)
- `generar_acta_pdf(request, asignacion_pk)` → WeasyPrint → PDF response
- `subir_acta_firmada(request, asignacion_pk)` → upload escaneado

**Forms nuevos (agregar a forms.py):**
- `AsignacionForm` — usuario, observaciones
- `DevolucionForm` — observaciones
- `TrasladoForm` — usuario_destino, observaciones
- `SubirActaForm` — escaneado_firmado

---

### SUB-ETAPA 3D — Templates lista + detalle

**Archivos a crear:**
```
backend/inventario/templates/inventario/lista.html
backend/inventario/templates/inventario/partials/tabla.html
backend/inventario/templates/inventario/detalle.html
```

**lista.html:** extends base.html · filtros tipo/estado/búsqueda HTMX · stats cards (total/asignados/disponibles/baja) · tabla responsive

**partials/tabla.html:** solo tabla — target HTMX para búsqueda en vivo

**detalle.html:** ficha activo · campos según tipo · badge estado · asignación actual (card) · historial movimientos (timeline) · actas (lista con botón subir firmada) · botones editar/dar de baja/asignar

---

### SUB-ETAPA 3E — Templates form + acta PDF

**Archivos a crear:**
```
backend/inventario/templates/inventario/form.html
backend/inventario/templates/inventario/asignacion_form.html
backend/inventario/templates/inventario/acta_pdf.html    ← WeasyPrint
```

**form.html:** form dinámico — campos comunes siempre visibles + secciones colapsables por tipo (JS oculta/muestra según select tipo_dispositivo)

**asignacion_form.html:** form simple para asignar/devolver/trasladar

**acta_pdf.html:** template limpio sin sidebar para WeasyPrint — logo empresa + datos activo + datos usuario + fecha + espacio firma

---

### SUB-ETAPA 3F — Patches + integración

**Archivos a modificar:**
```
backend/sysadmin/settings/base.py   ← activar 'inventario' en INSTALLED_APPS
backend/sysadmin/urls.py            ← agregar path inventario
backend/core/views.py               ← stats inventario en dashboard
backend/templates/base.html         ← quitar disabled del link Inventario en sidebar
```

**Stats dashboard (core/views.py):**
```python
from inventario.models import Activo
"total_activos": Activo.objects.count(),
"activos_asignados": Activo.objects.filter(estado="asignado").count(),
"activos_disponibles": Activo.objects.filter(estado="disponible").count(),
```

---

## CONVENCIONES DEL PROYECTO (respetar siempre)

1. Nunca eliminar registros — solo desactivar/dar de baja
2. Todos los modelos: `fecha_creacion` auto + `fecha_actualizacion` auto_now
3. Login requerido en todas las vistas (`@login_required`)
4. HTMX en listas: partial devuelto cuando `HX-Request` header presente
5. Mensajes Django (`messages.success/warning/error`) en todas las acciones
6. Namespace en todas las apps URLs (`app_name = "xxx"`)
7. Templates extienden `base.html` — bloque `{% block content %}`
8. CSS: solo variables `--sa-*`, clases Bootstrap 5.3
9. PDFs: WeasyPrint con template separado `*_pdf.html`
10. Formularios: widgets con `class="form-control"` o `class="form-select"`

---

## INSTRUCCIÓN PARA LA IA EN NUEVO CHAT

```
Proyecto: SysAdmin (sistema gestion IT)
Stack: Django 4.2 · PostgreSQL 15 · Bootstrap 5.3 · HTMX · Docker Compose
Etapas 0, 1, 2 completas. Iniciando Etapa 3 — inventario, sub-etapa [INDICAR: 3A/3B/3C/3D/3E/3F].
Respetar design system --sa-*, convenciones del proyecto, nunca recrear archivos existentes.
Terse responses. Código completo. Sin fluff.
```

---

## REQUIREMENTS.TXT ACTUAL

```
Django==4.2.13
gunicorn==21.2.0
psycopg2-binary==2.9.9
WeasyPrint==60.2
openpyxl==3.1.2
cryptography==42.0.8
argon2-cffi==23.1.0
python-decouple==3.8
Pillow==10.3.0
django-htmx==1.17.3
qrcode==8.2
django-axes==8.3.1        ← FASE 7: rate limit/lockout del login
```

> **Nota:** `backend/requirements.txt` es la fuente de verdad de dependencias (el build de Docker la instala desde `./backend`). El duplicado de la raíz se eliminó en 2026-09-24 para evitar divergencias.

---

## COMANDOS POST-ETAPA 3A (ejecutar tras copiar archivos)

```bash
docker exec -it sysadmin_django python manage.py migrate
docker exec -it sysadmin_django python manage.py collectstatic --noinput
docker compose restart django
```

---

## ACTUALIZACIÓN 2026-09-03 — v1.1.0

### Resumen
Release que consolida estabilización del sistema, mejora el módulo de inventario y agrega el módulo de documentos.

### Nuevo módulo: `documentos`

**Modelos (`documentos/models.py`)**
- `Categoria`: nombre, descripción, orden
- `Documento`: título, descripción, categoría FK, tipo (manual/procedimiento/política/general), archivo, versión, fecha de versión, activo, usuario creador

**Vistas (`documentos/views.py`)**
- `lista_documentos` — listado con filtros por texto, tipo y categoría
- `crear_documento`, `editar_documento`, `eliminar_documento`
- `descargar_documento` — descarga directa del archivo
- `lista_categorias`, `crear_categoria`, `editar_categoria`, `eliminar_categoria`

**Templates**
- `lista.html`, `form.html`, `categorias_lista.html`, `confirmar_eliminar.html`, `confirmar_eliminar_categoria.html`

**URLs namespace `documentos`**
- `/documentos/`
- `/documentos/nuevo/`
- `/documentos/<pk>/editar/`
- `/documentos/<pk>/eliminar/`
- `/documentos/<pk>/descargar/`
- `/documentos/categorias/`

### Mejoras en inventario
- `Activo.catalogo`: FK opcional a `CatalogoModelo`; el formulario ahora autocompleta marca y modelo al seleccionar un catálogo
- `Activo.nombre_equipo`: nuevo campo para equipos escritorio/portátil
- Endpoint JSON `/inventario/catalogo/json/` para filtrar catálogos por tipo
- Fix de errores visuales en `detalle.html` y `sysadmin.css`
- Fix de errores 500 en mantenimiento, asignaciones, reportes y exportación PDF
- Exportación Excel de inventario mejorada (48 columnas con estilo)

### Infraestructura y estabilidad
- Puerto de acceso cambiado de `6000` a `6060` (evita `ERR_UNSAFE_PORT`)
- Healthcheck en servicio Django y Nginx depende de `condition: service_healthy`
- `SECRET_KEY` real en `.env`
- Pin de `pydyf==0.10.0` para evitar error en WeasyPrint

### Archivos creados/modificados relevantes
- Creados: `backend/documentos/`, `backend/inventario/migrations/0004_activo_nombre_equipo.py`, `backend/inventario/migrations/0005_activo_catalogo.py`
- Modificados: `backend/inventario/*`, `backend/sysadmin/settings/base.py`, `backend/sysadmin/urls.py`, `backend/templates/base.html`, `backend/reports/views.py`

### Comandos post-deploy v1.1.0
```bash
docker compose exec django python manage.py migrate inventario
docker compose exec django python manage.py migrate documentos
docker compose exec django python manage.py collectstatic --noinput
docker compose restart django
```

---

## ACTUALIZACIÓN 2026-09-04 — Reportes configurables

### Resumen
Mejoras post-release sobre los reportes de inventario: export Excel/PDF ahora comparten la misma pantalla de configuración, permiten filtrar por tipo de dispositivo y elegir qué columnas exportar.

### Excel de inventario
- Hoja única "Inventario" que combina lista de activos + resumen por categorías + totales.
- 48 campos disponibles a través de `/inventario/exportar/opciones/`.
- Logo proporcional calculado con PIL, centrado en área A1:B1.
- Banner con texto desplazado a columna C para no tapar el logo.
- Configuración de página horizontal, ajuste a ancho y centrado horizontal.
- Anchos de columna calculados solo sobre filas de datos, sin incluir el resumen.

### PDF de inventario
- Nuevo diseño con banner de marca, fichas/tarjetas por activo y cards de resumen.
- Columnas configurables: se construyen dinámicamente desde `CAMPOS_INVENTARIO`.
- Filtro por tipo de dispositivo.
- Badges de estado con colores según el estado crudo.
- Valor total solo aparece si se incluye `valor_compra` entre los campos.
- Se abre en nueva pestaña desde la pantalla de opciones.

### Pantalla de opciones (`/inventario/exportar/opciones/`)
- Selector de formato: Excel o PDF.
- Filtro multi-select por tipo de dispositivo con JS que oculta/muestra secciones de columnas.
- Checkboxes de columnas agrupados por sección.
- Botones "Reporte completo" y "Generar con selección".
- La acción del formulario cambia vía JS según el formato elegido.

### Archivos creados/modificados relevantes
- Creado: `backend/inventario/templates/inventario/inventario_exportar_opciones.html`
- Modificados: `backend/reports/views.py`, `backend/reports/templates/reports/inventario_pdf.html`, `backend/reports/templates/reports/index.html`, `backend/inventario/views.py`, `backend/inventario/urls.py`

### Commits
- `4ab2594` feat(reports): reporte de inventario configurable en PDF/Excel con filtros y estilo de marca
- `a7a0258` docs: actualiza docs/sesiones/SESION_2026-09-04_RESUMEN con hash final 4ab2594

---

## ACTUALIZACIÓN 2026-09-09 — Importación masiva Activos + Usuarios + Plantillas Excel

### Resumen
Implementación de importación masiva desde Excel para Activos e Usuarios, siguiendo el mismo patrón: subir archivo → vista previa con estado por fila → confirmar creación. Incluye plantillas Excel descargables con ejemplos e instrucciones.

### Importación masiva de Activos (`/inventario/importar/`)
- **Parser robusto**: Lee primera hoja .xlsx, mapea headers por label exacto contra `CAMPOS_INVENTARIO` (39 campos soportados)
- **Normalización automática**:
  - Tipo de dispositivo: "Portátil" → `portatil`, "Equipo Escritorio" → `escritorio`, etc.
  - Estado: "Disponible" → `disponible`, "En mantenimiento" → `en_mantenimiento`, etc.
  - Booleanos: "Sí/No" → True/False
  - Moneda: "$1.234.567" → 1234567.0
  - Fechas: "2024-03-15" / "15/03/2024" / "15-03-2024" → ISO string
  - Pulgadas: "15,6" → 15.6
- **Vista previa**: Tabla con Tipo/Marca/Modelo/Serial + badge estado:
  - ✅ **OK** (tiene serial + tipo)
  - ⚠️ **Ya existe — se omite** (serial ya en BD)
  - ❌ **Error: falta serial** / **Error: falta tipo**
- **Race guard**: Doble verificación de serial en confirmación (evita duplicados entre preview y confirmar)
- **Plantilla Excel descargable** (`/inventario/importar/plantilla/`): 39 columnas, 2 filas ejemplo (Portátil + Celular), hoja Instrucciones completa

### Importación masiva de Usuarios (`/usuarios/importar/`)
- Mismo patrón: subir → preview → confirmar
- Parser reordena nombre: "Calle Rivera Bairon Nicolas" → "Bairon Nicolas Calle Rivera"
- Valida: Identificación única, Nombre obligatorio
- **Plantilla Excel descargable** (`/usuarios/importar/plantilla/`): 6 columnas, 2 ejemplos, hoja Instrucciones con formato de nombre

### UI
- Botón "Descargar plantilla" en ambas pantallas de importación
- Badges de estado con colores consistentes (OK=success, Duplicado=warning, Error=danger)

### Archivos creados/modificados
- Creados: `backend/inventario/templates/inventario/importar.html`, `importar_preview.html`
- Creados: `backend/usuarios/views.py` (+descargar_plantilla_usuarios), `backend/usuarios/urls.py` (+plantilla)
- Modificados: `backend/inventario/views.py` (+LABEL_TO_CAMPO, _normalizar_valor, _parsear_excel_activos, importar_activos, confirmar_importar_activos, descargar_plantilla_activos), `backend/inventario/urls.py`, `backend/inventario/templates/inventario/lista.html`, `backend/usuarios/templates/usuarios/importar.html`

### Commits
- `d952a6f` feat: importación masiva Activos + Usuarios con plantillas Excel

---

## CHANGELOG

### 2026-05-04 — Revisión y corrección Etapa 3 (3A–3C)

**Hallazgos corregidos:**

1. **`pdf_generado` obligatorio en `ActaAsignacion`** → Cambiado a `null=True, blank=True`.
   La vista `generar_acta_pdf` ahora persiste el PDF en el FileField usando `ContentFile`
   la primera vez que se genera.

2. **CRUD `CatalogoModelo` faltante** → Añadidas 3 vistas (`lista_catalogo`, `crear_catalogo`,
   `editar_catalogo`) en `views.py` y sus URLs en `urls.py`.
   Template pendiente: `inventario/catalogo_lista.html` (crear en 3D).

3. **URLs de movimientos 3C no mapeadas** → `urls.py` actualizado con las 5 rutas:
   `asignar`, `devolver`, `trasladar`, `acta_pdf`, `subir_acta`.

**Archivos modificados:**
- `inventario/models.py` — línea 194: `pdf_generado` ahora nullable
- `inventario/views.py` — import `ContentFile` + `CatalogoModelo`, fix `generar_acta_pdf`, CRUD catálogo
- `inventario/urls.py` — rutas completas (CRUD + movimientos + catálogo)

**Pendiente para migración:**
```bash
docker exec -it sysadmin_django python manage.py makemigrations inventario
docker exec -it sysadmin_django python manage.py migrate
```

### 2026-05-04 — Sub-etapa 3D: Templates lista + detalle

**Archivos creados:**
- `inventario/templates/inventario/lista.html` — Vista principal con stats cards, filtros HTMX, tabla
- `inventario/templates/inventario/partials/tabla.html` — Partial HTMX con íconos por tipo, badges de estado
- `inventario/templates/inventario/detalle.html` — Ficha completa: specs por tipo, asignación actual, timeline movimientos, actas
- `inventario/templates/inventario/catalogo_lista.html` — Lista filtrable del catálogo con specs JSON como badges

**Design system respetado:**
- Clases `sa-card`, `sa-table`, `sa-stat-icon`, `sa-stat-value`, `sa-stat-label`
- Variables CSS `--sa-primary-light`, `--sa-font-mono`, `--sa-bg`, `--sa-border`
- Bootstrap 5.3 badges subtle, Bootstrap Icons
- HTMX con `hx-get`, `hx-target`, `hx-trigger`, `hx-push-url`

---

### 2026-05-04 — Sub-etapa 3E: Templates form + acta PDF

**Archivos creados:**
- `inventario/templates/inventario/form.html` — Formulario dinámico de activos: secciones colapsables por tipo (celular/escritorio+portátil/teléfono/monitor) controladas por JS vanilla inline. Toggle para garantía extendida.
- `inventario/templates/inventario/asignacion_form.html` — Form genérico reutilizable para asignar/devolver/trasladar/subir acta. Ícono y texto del botón se adaptan según `accion` en contexto.
- `inventario/templates/inventario/acta_pdf.html` — Template WeasyPrint puro A4 (sin sidebar/base.html). Tablas de datos con filas condicionales por tipo de dispositivo, cláusula legal, 3 espacios de firma (empleado, sistemas, jefe).

**Nota técnica `form.html`:**
- JS inline dentro de `{% block content %}` (no depende de `{% block extra_js %}` en base.html).
- En modo editar: `toggleSecciones()` se dispara al cargar para mostrar la sección correcta según el tipo del activo existente.

### 2026-05-04 — Sub-etapa 3F: Patches + integración

> ⚠️ Histórico: el flujo de "aplicar patches a mano en servidor" quedó reemplazado
> por el deploy vía Docker (`docker compose up -d --build`). Los archivos
> `INSTRUCCIONES_PATCHES*.txt` fueron eliminados por obsoletos (2026-09-24).

**Cambios que aplicaban (para contexto histórico):**
1. `backend/sysadmin/settings/base.py` → descomentar `"inventario"` en INSTALLED_APPS
2. `backend/sysadmin/urls.py` → agregar `path("inventario/", include("inventario.urls", namespace="inventario"))`
3. `backend/core/views.py` → agregar import `Activo` y 4 stats al contexto del dashboard
4. `backend/templates/base.html` → quitar `disabled` del link Inventario en sidebar
5. `backend/usuarios/views.py` → (bonus) conectar activos reales en `detalle_usuario`

**Estado final:** Todo el código del módulo inventario está listo e integrado en el repo.

---

### 2026-05-04 — Reconstrucción de Entorno Local (Post-Etapa 3F)

**Contexto:** Los archivos locales solo contenían las aplicaciones `usuarios` e `inventario` sueltas, faltando toda la estructura principal de Django y los archivos necesarios para levantar Docker localmente de acuerdo al `docker-compose.yml`.

**Acciones realizadas (Sin borrar código existente):**
- Se creó la carpeta `backend/` y se movieron las carpetas y archivos de `usuarios` e `inventario` hacia adentro para respetar la estructura de Docker.
- Se reconstruyó la fundación (Etapas 0 y 1 perdidas localmente):
  - `backend/manage.py` y `backend/sysadmin/settings/base.py` + `urls.py`.
  - Aplicación mínima `accounts` (con `CustomUser` y `login.html`).
  - Aplicación mínima `core` (con vista `dashboard`).
  - Template `backend/templates/base.html` con sidebar, Bootstrap 5.3 y HTMX.
  - `backend/Dockerfile` y `nginx/Dockerfile` + `nginx.conf`.

**Estado final:** El código local ahora tiene la estructura de un proyecto completo. Ya es posible ejecutar `docker compose up -d --build` localmente para probar los módulos, realizar migraciones y validar todo el trabajo de Inventario antes de llevarlo al servidor Ubuntu real.

---

*Última actualización: 2026-05-04 · Etapa 3 completa · Entorno local reconstruido y listo para testeo Docker*

---

*Última actualización: 2026-06-05 · Yule 7B completa · Proyecto 100% funcional*

---

## CHANGELOG RECIENTE

### 2026-09-24 — Deploy producción completado (Docker Compose · 192.168.1.250) · migración de datos

- **Contenedores 3/3 arriba**: `sysadmin_db` (postgres:15-alpine, healthy), `sysadmin_django` (healthy), `sysadmin_nginx` (started). Conviven con el stack Hikvision (puertos/red/volúmenes propios, sin colisión).
- **Acceso**: `https://192.168.1.250:6060` (nginx SSL → django), `http://192.168.1.250:6061` → 301 → https. Cert autofirmado CN=192.168.1.250 (825 días) en `nginx/certs/`.
- **Fix redirect-loop (crítico)**: `backend/sysadmin/settings/base.py` ahora define `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`. Sin esto, con `SECURE_SSL_REDIRECT=True` + `DEBUG=False`, Django ignora el `X-Forwarded-Proto` de nginx y 301-redirige todo → healthcheck entra en loop → `unhealthy`. El healthcheck de django en `docker-compose.yml` manda `X-Forwarded-Proto: https` para que responda 200.
- **`.env` producción**: `DEBUG=False`, `SECRET_KEY`, `PASSWORDS_ENCRYPTION_KEY`, `POSTGRES_PASSWORD` + flags de seguridad `True`. Invalidado con `unofficial` superuser `Administrador`.
- **Migración de datos**: `pg_dump -Fc` del SysAdmin local (contenedor `sysadmin_db`) → `scp` → `pg_restore --clean --if-exists --no-owner --no-privileges` en el servidor. Conteos verificados desde el propio `sysadmin_db`: 67 usuarios_usuario · 23 activos · 2 documentos · 1 credencial · 1 ticket. Login real corre sobre `accounts.CustomUser` (2 superusuarios); `usuarios.usuario` es el registro de personal/activantes (sin `username`/`is_superuser` — no confundir con el modelo de login).
- **Pendientes**: (1) backups a NAS — `backup.sh` en `/opt/sysadmin/backups/` sin destino configurado ni cron (el cron actual del server es de Hikvision, no pisar); (2) OCS/Yule — endpoint no configurado en el servidor (`Error OCS: OCS no está configurado`), solo agregar credenciales/endpoint para activar sincronización.

### 2026-09-24 — v1.10.0 · Seguridad del login + HTTPS interno (Fase 7)

- **django-axes 8.3.1**: rate limit/lockout por usuario+IP (5 intentos → bloqueo 1h), reset por login exitoso. Reemplaza `accounts.middleware.LoginRateLimitMiddleware` (eliminado). Dependencia `django-axes==8.3.1` en `requirements.txt` (raíz). Migraciones de axes aplicadas.
- **Mensajes genéricos de login**: `accounts/forms.py` → `SysAdminAuthenticationForm` ("Usuario o contraseña incorrectos." / "Esta cuenta está inactiva…"), conectado en `accounts/urls.py`.
- **Auditoría de fallos**: `accounts/signals.py` registra `login_fallido` (señal `user_login_failed`) y `cuenta_bloqueada` (señal `user_locked_out` de axes) en `RegistroAuditoria` con usuario+IP. Cargado desde `accounts/apps.py::ready()`.
- **Password validators**: `AUTH_PASSWORD_VALIDATORS` con `MinimumLength(min_length=10)` + simitud + comunes + numéricos.
- **Headers de seguridad**: `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`, `SECURE_REFERRER_POLICY=same-origin` (verificados en runtime).
- **Cookies de sesión**: `HttpOnly`, `SameSite=Lax`, `SESSION_COOKIE_AGE=28800` (8 h), `SESSION_EXPIRE_AT_BROWSER_CLOSE=True`.
- **HTTPS interno LAN**: cert autofirmado en `nginx/certs/` (CN=192.168.1.250, 825 días); `nginx/nginx.conf` con server 443 ssl + redirect 301 desde puerto 80; `docker-compose.yml` con `6060:443` (https) y `6061:80` (http→https), volumen `./nginx/certs`; CSRF trusted origins https.
- **Tests**: `LoginSeguridadTests` en `accounts/tests.py` (+11); `administracion`/`soporte` migrados a `force_login`. Suite completa **313/313 OK** · `manage.py check` 0 issues.
- **Login "reportar falla" en nueva pestaña** (`26d0a6d`): `accounts/templates/accounts/login.html` con `target="_blank" rel="noopener"`.
- ⚠️ **SIN COMMITEAR**: los cambios de seguridad (10 modificados + 1 eliminado + 3 nuevos) quedan en el working tree para revisión del arquitecto. Ver `docs/sesiones/SESION_2026-09-24_RESUMEN.md`.

### 2026-09-10 — v1.9.0 · Cierre del plan por fases (11 commits ejecutados)

- Ejecutados los **9 commits del sprint** (agrupación §13 del resumen): `1565d08` (security), `f329696` (etiquetas QR, alerta "hasta 24 por hoja A4"), `e4dcac2` (mantenimiento), `9f6524f` (soporte), `d9dd3b9` (licencias), `4a17326` (prestamos), `d8b7033` (cobertura), `4c52b9d` (drift migraciones), `5094cba` (docs v1.8.1).
- **Detector de licencias en notificaciones** (`c9f18ac`): nuevo tipo `licencia` en `Notificacion.TIPOS` y choice `contrato` en `TIPOS_LICENCIA`. `_detectar_licencias` marca vencidas/póximo-vencimiento a 7 días (excluye canceladas y sin fecha), con `objetokey="licencia:<pk>"` e idempotencia. Migraciones `licencias/0002` y `notificaciones/0002`. 6 tests nuevos.
- **Gestión de cuentas de usuario** (`36d58bb`): `/administracion/cuentas/` con listado + búsqueda HTMX, crear (password temporal mostrada una sola vez), cambiar rol, activar/desactivar (guardas anti auto-desmoción/auto-desactivación) y resetear contraseña. **`is_superuser`/`is_staff` solo para rol `superadmin`** (el rol app `admin` queda en `/administracion/`, NO entra a `/admin/`). Vistas `lista_cuentas`, `crear_cuenta`, `cambiar_rol_cuenta`, `toggle_cuenta`, `resetear_password`; forms `CuentaForm`/`CuentaRolForm`; templates `cuentas_lista`/`cuenta_form`/`cuenta_rol`/`partials/tabla_cuentas` + botón "Cuentas" en auditoría. 8 tests nuevos.
- **Verificación final**: suite **217/217 OK** · `manage.py check` 0 issues · `makemigrations --check` sin cambios · working tree limpio · `.env` y `db.sqlite3` no versionados.

### 2026-09-10 — Corrección BD local + drift de migraciones

- `db.sqlite3` local estaba roto: historial de migraciones inconsistente pre-existente (falta `accounts.0001`/`accounts.0002` y la tabla `accounts_customuser`; apps antiguas creadas por syncdb), sin datos de negocio. Se reconstruyó de cero con `migrate` → **42 migraciones aplicadas** en orden.
- Superuser dev `admin` (rol `superadmin`) y singleton `ConfiguracionSistema` creados. La BD antigua quedó respaldada en `backend/db.sqlite3.legacy_20260910`.
- Drift resuelto: `yule/0002` (renombres de índices) y `administracion/0002` (choices de `modulo` sincronizados con los módulos nuevos de las Fases 4-6). `makemigrations --check` → *No changes detected*.
- Suite completa **202/202 OK** · `manage.py check` 0 issues · `makemigrations --check` sin drift.

### 2026-09-10 — Fase 4: Tests de cobertura

- Tests para `core`, `usuarios`, `mantenimiento`, `documentos`, `passwords`, `reports`, `yule` (81 nuevos).
- Fix producción: `passwords/views.py` registraba `AccesoLog` después de borrar el objeto (vault/credencial) → `ValueError: save() prohibited`; el log ahora precede al `delete()`.
- PDFs de `reports` probados con WeasyPrint mockeado en `sys.modules` (patrón Fase 2, sin GTK).
- Suite completa: 142/142 tests OK, `manage.py check` 0 issues.

### 2026-09-10 — Fase 3: Mantenimiento completo (checklist + criticidad + calendario + reportar)

- **Notificaciones**: app `notificaciones` con detectores perezosos (garantía, mantenimiento, actas, OCS), vistas bandeja/cantidad/marcar_leida, campana HTMX en sidebar. Fix `_detectar_actas` (field vacío `""` detectado además de NULL). Mgmt command `generar_notificaciones_mantenimiento`.
- **Checklist**: modelo `ChecklistItem` (plan plantilla → copia a orden al crear). Formset de items en crear/editar plan. Toggle completado vía HTMX (`partials/checklist_orden.html`) con barra de progreso en detalle de orden.
- **Criticidad**: campo `criticidad` (`baja/media/alta`) en `PlanMantenimiento` con badge de color en tabla de planes y en el detalle del plan.
- **Estado `reportada`** añadido a `OrdenMantenimiento`.
- **Calendario**: FullCalendar (CDN) + endpoint JSON `calendario_eventos` mostrando ordenes y planes preventivos con colores por estado/criticidad.
- **Portal de reporte**: `/mantenimiento/reportar/` — `@login_required`, sin permiso de módulo. Crea `OrdenMantenimiento` con estado `reportada`, tipo `correctivo`, prioridad `alta`. Enlace visible en sidebar para todos los usuarios autenticados.
- 12 tests nuevos (checklist plan→orden 3, toggle 1, command idempotente 1, reporte portal 4, calendario 2) → suite total **153/153** OK.
- Migración: `mantenimiento/0002_..._criticidad_and_more.py` generada con `sysadmin.settings._tmp_scratch` (SQLite temporal, eliminado después).

### 2026-09-10 — Fase 6: Préstamos de equipos (app `prestamos`)

- Modelo `Prestamo`: activo FK (PROTECT) a `inventario.Activo`, solicitante FK (PROTECT) a usuario, fecha_prestamo (default hoy), fecha_devolucion_prevista, fecha_devolucion, destino, observaciones; índice `(fecha_prestamo, fecha_devolucion_prevista)`.
- Estado calculado: devuelto > vencido (prevista pasada) > activo; `dias_retraso` para vencidos.
- Validación `PrestamoForm`: bloquea un segundo préstamo vigente del mismo equipo y previstas anteriores al préstamo.
- CRUD + "Registrar devolución" (POST idempotente); sin vista de eliminar (se preserva el historial).
- Módulo `prestamos` en `PERMISOS_POR_ROL`: superadmin/admin/tecnico = escritura; lectura = lectura. Sidebar tras Licencias.
- Migración `prestamos/0001_initial` generada y validada en BD limpia temporal (`_tmp_scratch`, eliminada).
- 16 tests en `prestamos/tests.py` → suite total **202/202** OK, `manage.py check` 0 issues.
- 🏁 **Plan por fases completado (1-6).**

### 2026-09-10 — Fase 5: Licencias de software (app `licencias`)

- Modelo `LicenciaSoftware`: nombre, version, proveedor, clave/serial, tipo (volumen/individual/oem/suscripcion), cantidad, fechas compra/vencimiento, costo, estado (activa/cancelada), responsable, observaciones, timestamps.
- M2M opcional `activos` → `inventario.Activo` con related_name `licencias`.
- Estado efectivo computado (`estado_efectivo`): cancelada > vencida (> fecha) > por_vencer (≤7 días) > activa; filtro de lista por estado efectivo.
- CRUD completo + detalle con equipos cubiertos + eliminar con confirmación.
- Migración `licencias/0001_initial` generada y validada en BD limpia temporal (`_tmp_scratch`, eliminada).
- Módulo `licencias` en `PERMISOS_POR_ROL`: superadmin/admin = escritura; tecnico/lectura = lectura. Sidebar entre Mantenimiento y Documentos.
- Exports Excel (openpyxl) y PDF (weasyprint lazy) con patrón `CAMPOS_LICENCIAS` (mismo estándar que `CAMPOS_INVENTARIO`).
- Nuevo filtro genérico `get_item` en `accounts/templatetags/permisos_extras.py`.
- 19 tests en `licencias/tests.py` → suite total **186/186** OK, `manage.py check` 0 issues.

### 2026-09-10 — Fase 4 (plan): Helpdesk / Tickets (app `soporte`)

- Modelo `Ticket`: asunto, descripcion, prioridad, estado (abierto/en_proceso/resuelto/cerrado/escalado), solicitante FK (PROTECT), asignado_a FK (SET_NULL), índice (estado, fecha_creacion).
- Módulo `soporte` añadido a `PERMISOS_POR_ROL`: superadmin/admin/tecnico = escritura; lectura = lectura. `crear_ticket` es portal abierto (`@login_required`).
- `asignar_ticket` guarda asignación, pasa a `en_proceso` y notifica al técnico vía `notificaciones.services.aviso_usuario` (idempotente; reasignar no duplica).
- `escalar_ticket` crea `OrdenMantenimiento` (correctivo/abierta) con nueva FK opcional `ticket` en `OrdenMantenimiento`, heredando la prioridad; el ticket pasa a `escalado` y no se puede duplicar la orden.
- Sidebar: enlace "Soporte" condicional por rol.
- 14 tests en `soporte/tests.py` → suite total **167/167** OK, `manage.py check` 0 issues.
- Migraciones: `soporte/0001_initial` + `mantenimiento/0003_ordenmantenimiento_ticket` (generadas con BD temporal `_tmp_scratch`, eliminada).

### 2026-09-10 — Fase 4 EXTRA: Tests de cobertura (todas las apps)

- Tests nuevos: core (3), usuarios (12), mantenimiento (16), documentos (11), passwords (17), reports (12), yule (10) → 81 tests.
- Fix producción: `passwords/views.py` `AccesoLog` registrado antes del `delete()` (corregido durante la escritura de tests de passwords).
- Mock de WeasyPrint en tests de reports: `patch.dict("sys.modules", {"weasyprint": _FakeWeasyprint})`.
- Suite completa: 153/153 tests OK, `manage.py check` 0 issues.

### 2026-09-10 — Fase 2: Etiquetas QR para activos

- `qrcode==8.2` (PNG puro, sin GTK). QR cifra URL absoluta de la ficha.
- Endpoints: `/<pk>/qr/` (PNG), `/<pk>/etiqueta/` (PDF 50×30 mm), `/etiquetas/` (selección masiva → PDF A4, 8 por hoja).
- Plantillas: `etiqueta_pdf.html` (WeasyPrint) y `etiquetas_seleccion.html` (web).
- Integración: botón en lista, icono QR por fila en tabla, vista previa + botón en detalle.
- 10 tests en `inventario/tests.py`.

### 2026-09-10 — Fase 1: Módulo de Administración (roles + permisos + auditoría)

- Roles `superadmin`/`admin`/`tecnico`/`lectura` + matriz `PERMISOS_POR_ROL`.
- Decorador `@requiere_permiso` en todas las vistas de todos los módulos.
- App `administracion`: `RegistroAuditoria` (signals login/logout), `ConfiguracionSistema` (singleton).
- Sidebar condicional por rol (template tag `tiene_permiso`).
- WeasyPrint con imports locales (herramientas de desarrollo habilitadas sin GTK).
- Suite completa: 30 tests OK (accounts + administracion + inventario + yule).

### 2026-06-05 — Yule 7B Completada

**Etapa 7B — Sincronización OCS Inventory NG**

Implementación completa (~1900 líneas de código):

**Backend:**
- `yule/models.py`: EquipoOCS, SincronizacionLog, ConfiguracionYule (3 modelos, 4 índices)
- `yule/client.py`: OCSClient con retry logic exponencial, 3 tipos de excepciones, timeout configurable
- `yule/sync.py`: sincronizar_equipos_ocs() con búsqueda de matches (serial/MAC/hostname)
- `yule/views.py`: 7 vistas (dashboard, lista, detalle, sin-match, historial, sincronizar, test-API)
- `yule/admin.py`: Admin customizado con badges, filtros, formateo de estadísticas
- `yule/management/commands/sync_ocs.py`: Comando CLI con flags --force y --user

**Frontend:**
- 5 templates HTML responsive (Bootstrap 5)
- Dashboard con config, conexión status, estadísticas
- Lista paginada con filtros HTMX
- Historial auditoría con badges de estado

**Características:**
- ✅ Sincronización manual (web, admin, CLI)
- ✅ Retry logic con exponential backoff (1s, 2s, 4s)
- ✅ Búsqueda automática de matches en inventario local
- ✅ Auditoría completa de todas las sincronizaciones
- ✅ Management command para automatización futura

**Estado:** LISTO PARA TESTING EN SERVIDOR

**Próximos pasos:**
```bash
# En servidor
docker exec -it sysadmin_django python manage.py migrate yule
# Configurar .env con credenciales OCS reales
docker exec -it sysadmin_django python manage.py sync_ocs --force
```

---

### 2026-06-05 — Consolidación de Documentación

- Documentación de Yule 7B integrada en README.md (sección completa)
- Documentación de Yule 7B integrada en SYSADMIN_HANDOFF.md
- Archivos separados YULE_7B.md y YULE_7B_COMPLETADO.md eliminados
- Single source of truth: todo en README.md y HANDOFF

---

### Notas Previas (Archivo para referencia)

#### 2026-05-05 — Reportes 4A

- Etapa 4A implementada: tablero de reportes con indicadores base.
- Exportables disponibles: PDF inventario + Excel inventario y movimientos.
- Filtros por rango (default 30 dias) para movimientos.

**Archivos actualizados:**
- `backend/reports/views.py` — contexto de reportes, filtros por rango, exports PDF/Excel.
- `backend/reports/urls.py` — rutas de export.
- `backend/reports/templates/reports/index.html` — tablero con tarjetas, tablas y filtros.

**Archivos creados:**
- `backend/reports/templates/reports/inventario_pdf.html` — template PDF WeasyPrint.

**Rutas nuevas:**
- `/reports/inventario/pdf/`
- `/reports/inventario/excel/`
- `/reports/movimientos/excel/`

**Pendiente sugerido (4B):**
- Reporte de costos (valor_compra) y amortizacion simple.
- Export Excel usuarios por area/cargo.
- KPI mensual de movimientos.

*Ultima actualizacion: 2026-05-05 · Etapa 4A completada en repo*

---

## ACTUALIZACION 2026-05-05 — 4B

---

### 2026-05-10 — Etapa 6A: Base tecnica passwords

**Cambios aplicados:**
- App `passwords` creada con modelos `Vault` y `Credencial` + migracion inicial.
- Rutas activadas en `sysadmin/urls.py` y sidebar visible solo para admin.
- Vista base `passwords/index.html` con listado inicial de vaults.

### 2026-05-10 — Etapa 6B: CRUD + UI passwords

**Cambios aplicados:**
- CRUD de vaults y credenciales (crear/editar/eliminar) con permisos admin.
- Vistas y templates: lista de vaults, lista de credenciales, formularios y confirmaciones.
- Filtros simples por texto/estado en credenciales.

### 2026-05-10 — Etapa 6C: Seguridad + cifrado

**Cambios aplicados:**
- Cifrado de secretos con `cryptography` (Fernet) y utilitario `passwords/crypto.py`.
- Hash de acceso por vault con `argon2` + flag `acceso_requerido`.
- Formulario de vault permite definir codigo de acceso; secretos no se muestran, solo se actualizan si se reescriben.
- Vista para desbloquear y mostrar secreto desde la lista de credenciales.
- Setting `PASSWORDS_ENCRYPTION_KEY` desde `.env` (fallback a `SECRET_KEY`).

### 2026-05-10 — Etapa 6D: Export + logs

**Cambios aplicados:**
- Modelo `AccesoLog` para auditoria de acciones (vault/credencial/usuario).
- Export Excel de credenciales (sin secretos) por vault.
- Vista de logs con filtros por accion y busqueda.

---

## HISTORIAL ORDENADO POR FECHA (RESUMEN)

### 2026-05-04
- Etapa 3 (3A–3F): inventario completo, templates 3D/3E, patches 3F documentados.
- Foundation reconstruida (Docker + Django base + accounts/core + base.html).

### 2026-05-05
- Reports 4A/4B: tablero, PDF/Excel y costos.

### 2026-05-06
- Mantenimiento: CRUD planes/ordenes/repuestos + acciones.

### 2026-05-10
- Passwords 6A–6D: app base, CRUD, cifrado y logs/export.
- `entrypoint.sh` + `.gitignore` agregados; Dockerfile actualizado para entrypoint.

- Reportes ampliados con costos y amortizacion simple (vida util 36 meses).
- KPI mensual de movimientos (ultimos 12 meses).
- Export Excel usuarios (resumen por area/cargo + listado) y costos.

## DETALLE ETAPA 4B (reports)

**Archivos actualizados:**
- `backend/reports/views.py` — KPI mensual, costos/amortizacion, exports nuevos.
- `backend/reports/urls.py` — rutas /usuarios/excel y /costos/excel.
- `backend/reports/templates/reports/index.html` — seccion costos + KPI mensual + botones export.

**Rutas nuevas:**
- `/reports/usuarios/excel/`
- `/reports/costos/excel/`

**Notas tecnicas:**
- Amortizacion lineal por meses desde fecha_compra.
- Top 8 activos por valor actual estimado en tablero.
- Sin migraciones nuevas.

*Ultima actualizacion: 2026-05-05 · Etapa 4B completada en repo*

---

## ACTUALIZACION 2026-05-05

- Etapa 4 (reports) avanzada a tablero funcional con exportables.
- Reportes ahora incluyen resumen de inventario por estado/tipo, usuarios por area y movimientos en rango.
- Exportables disponibles: PDF inventario y Excel inventario/movimientos.
- Filtros por rango de fechas para movimientos con default 30 dias.

## ESTADO ACTUALIZADO

| Etapa | Modulo | Estado |
|-------|--------|--------|
| 0 | Fundacion Docker+Django+Nginx | ✅ COMPLETA |
| 1 | accounts — Login/auth/sesion | ✅ COMPLETA |
| 2 | usuarios — BD personas | ✅ COMPLETA |
| 3 | inventario — Activos | ✅ INTEGRADO EN REPO · pendiente deploy en servidor |
| 4 | reports | 🟡 TABLERO BASE + EXPORTS (PDF/Excel) |
| 5 | mantenimiento | ⏳ |
| 6 | passwords | ⏳ |
| 7 | yule (OCS) | ⏳ |

## DETALLE ETAPA 4 (reports) — 4A

**Archivos actualizados:**
- `backend/reports/views.py` — contexto de reportes, filtros de rango, export PDF/Excel.
- `backend/reports/urls.py` — rutas de export: inventario PDF/Excel, movimientos Excel.
- `backend/reports/templates/reports/index.html` — tablero con tarjetas, tablas y filtros.

**Archivos creados:**
- `backend/reports/templates/reports/inventario_pdf.html` — plantilla PDF WeasyPrint para resumen.

**Rutas nuevas:**
- `/reports/inventario/pdf/` → PDF resumen inventario
- `/reports/inventario/excel/` → Excel resumen + listado de activos
- `/reports/movimientos/excel/` → Excel movimientos por rango

**Notas tecnicas:**
- No hay migraciones nuevas.
- Default de rango: ultimos 30 dias.
- Export Excel usa openpyxl (incluido en requirements).

**Pendiente Etapa 4 (4B sugerido):**
- Reporte de costos (valor_compra) y amortizacion basica.
- Export Excel de usuarios por area/cargo.
- Vista de KPIs mensuales (movimientos por mes).

*Ultima actualizacion: 2026-05-05 · Etapa 4A lista en repo*

---

## ETAPA 5 — MANTENIMIENTO: PLAN DE FRAGMENTACION

El modulo mantenimiento se divide en **5 sub-etapas**:

```
5A → Models + Migration
5B → Forms + Views CRUD
5C → Templates lista + detalle + form
5D → Programacion preventiva + alertas
5E → Integracion dashboard + reports
```

### SUB-ETAPA 5A — Models + Migration

**Archivos a crear:**
```
backend/mantenimiento/__init__.py
backend/mantenimiento/apps.py
backend/mantenimiento/models.py
backend/mantenimiento/admin.py
backend/mantenimiento/migrations/__init__.py
backend/mantenimiento/migrations/0001_initial.py
```

**Modelos requeridos (propuesta):**

`PlanMantenimiento`
- activo (FK inventario.Activo)
- tipo (preventivo/correctivo)
- frecuencia_dias (int)
- fecha_inicio, proxima_ejecucion
- estado (activo/pausado)
- responsable (CharField)
- observaciones
- fecha_creacion, fecha_actualizacion

`OrdenMantenimiento`
- plan (FK null) + activo (FK)
- tipo (preventivo/correctivo)
- estado (abierta/en_proceso/cerrada/cancelada)
- prioridad (baja/media/alta)
- fecha_apertura, fecha_cierre
- tecnico_asignado
- descripcion, diagnostico, acciones, costo_estimado, costo_real
- fecha_creacion, fecha_actualizacion

`Repuesto`
- nombre, referencia, cantidad, costo_unitario
- orden (FK OrdenMantenimiento)

### SUB-ETAPA 5B — Forms + Views CRUD

**Archivos a crear/modificar:**
```
backend/mantenimiento/forms.py
backend/mantenimiento/views.py
backend/mantenimiento/urls.py
```

**Vistas base:**
- lista_planes, detalle_plan, crear_plan, editar_plan, toggle_plan
- lista_ordenes, detalle_orden, crear_orden, editar_orden, cerrar_orden

### SUB-ETAPA 5C — Templates

**Archivos a crear:**
```
backend/mantenimiento/templates/mantenimiento/lista_planes.html
backend/mantenimiento/templates/mantenimiento/detalle_plan.html
backend/mantenimiento/templates/mantenimiento/lista_ordenes.html
backend/mantenimiento/templates/mantenimiento/detalle_orden.html
backend/mantenimiento/templates/mantenimiento/form_plan.html
backend/mantenimiento/templates/mantenimiento/form_orden.html
backend/mantenimiento/templates/mantenimiento/partials/tabla_planes.html
backend/mantenimiento/templates/mantenimiento/partials/tabla_ordenes.html
```

### SUB-ETAPA 5D — Programacion preventiva + alertas

**Objetivo:**
- Recalcular `proxima_ejecucion` al cerrar orden preventiva.
- Alertas visuales en listas: atrasadas, proximas (7 dias).

### SUB-ETAPA 5E — Integracion dashboard + reports

**Objetivo:**
- Contadores en dashboard (ordenes abiertas, atrasadas).
- Export Excel de ordenes por rango.

*Plan agregado: 2026-05-05 · Etapa 5 definida en sub-etapas*

---

## ACTUALIZACION 2026-05-05 — 5A

- App `mantenimiento` creada con modelos base y migracion inicial.
- Modelos: PlanMantenimiento, OrdenMantenimiento, Repuesto.
- Admin registrado para gestion inicial.

**Archivos creados:**
- `backend/mantenimiento/__init__.py`
- `backend/mantenimiento/apps.py`
- `backend/mantenimiento/models.py`
- `backend/mantenimiento/admin.py`
- `backend/mantenimiento/migrations/0001_initial.py`

**Notas tecnicas:**
- FK a `inventario.Activo` con `PROTECT`.
- Fechas y costos listos para CRUD en 5B.
- Sin integracion en settings/urls aun (se hara en 5E).

*Ultima actualizacion: 2026-05-05 · Etapa 5A completada en repo*

---

## ACTUALIZACION 2026-05-05 — 5B

- CRUD backend para mantenimiento (planes y ordenes) creado.
- App `mantenimiento` activada en settings y rutas publicadas.
- Intento de migracion ejecutado, pero el contenedor `sysadmin_django` no estaba disponible.

**Archivos creados:**
- `backend/mantenimiento/forms.py`
- `backend/mantenimiento/views.py`
- `backend/mantenimiento/urls.py`

**Archivos actualizados:**
- `backend/sysadmin/settings/base.py` — agregar `mantenimiento` a `INSTALLED_APPS`.
- `backend/sysadmin/urls.py` — ruta `/mantenimiento/`.

**Notas tecnicas:**
- Vistas incluyen filtros + HTMX partials para listas (planes y ordenes).
- `cerrar_orden` cierra orden y setea `fecha_cierre` si no existe.
- Validacion: si se selecciona plan, el activo debe coincidir.

**Comandos (fallaron por contenedor no existente):**
```bash
docker exec -it sysadmin_django python manage.py makemigrations mantenimiento
docker exec -it sysadmin_django python manage.py migrate
```

*Ultima actualizacion: 2026-05-05 · Etapa 5B backend completada en repo*


## ACTUALIZACION 2026-05-05 — Docker + migraciones

- Fix en Dockerfile backend: el build fallaba por `COPY ../requirements.txt` fuera del contexto.
- Se agrego `backend/requirements.txt` para el build local.
- Contenedores levantados y migraciones aplicadas.

**Archivos actualizados:**
- `backend/Dockerfile` — ahora copia `requirements.txt` desde el contexto.

**Archivos creados:**
- `backend/requirements.txt` — espejo del requirements raiz.

**Comandos ejecutados:**
docker compose up -d --build
docker exec -it sysadmin_django python manage.py makemigrations mantenimiento
docker exec -it sysadmin_django python manage.py migrate
```

- Templates completos para mantenimiento (planes y ordenes): listas, detalles y formularios.
- Listas con filtros HTMX + tarjetas de estado.
- Detalles con resumen + tablas de ordenes/repuestos.

**Archivos creados:**
- `backend/mantenimiento/templates/mantenimiento/lista_planes.html`
- `backend/mantenimiento/templates/mantenimiento/partials/tabla_planes.html`
- `backend/mantenimiento/templates/mantenimiento/detalle_plan.html`
- `backend/mantenimiento/templates/mantenimiento/form_plan.html`
- `backend/mantenimiento/templates/mantenimiento/lista_ordenes.html`
- `backend/mantenimiento/templates/mantenimiento/partials/tabla_ordenes.html`
- `backend/mantenimiento/templates/mantenimiento/detalle_orden.html`
- `backend/mantenimiento/templates/mantenimiento/form_orden.html`

**Notas tecnicas:**
- Vistas exponen choices para filtros (tipo/estado/prioridad).
- Breadcrumbs y estilos alineados al design system `--sa-*`.

*Ultima actualizacion: 2026-05-05 · Etapa 5C completada en repo*

---

## ACTUALIZACION 2026-05-05 — 5D

- Recalculo de `proxima_ejecucion` al cerrar orden preventiva.
- Alertas visuales en planes: atrasado (< hoy) y proximo (<= 7 dias).
- Check de Django OK tras cambios.

**Archivos actualizados:**
- `backend/mantenimiento/views.py` — logica de recalculo + contexto de alertas.
- `backend/mantenimiento/templates/mantenimiento/partials/tabla_planes.html` — badges atrasado/proximo.
- `backend/mantenimiento/templates/mantenimiento/detalle_plan.html` — badge de alerta en plan.

**Comandos ejecutados:**
```bash
docker exec -it sysadmin_django python manage.py check
```

*Ultima actualizacion: 2026-05-05 · Etapa 5D completada en repo*

---

## ACTUALIZACION 2026-05-05 — 5E

- Dashboard integra contadores de mantenimiento: ordenes abiertas y atrasadas.
- Reportes incluye export Excel de ordenes de mantenimiento por rango.

**Archivos actualizados:**
- `backend/core/views.py` — agrega contadores de mantenimiento.
- `backend/core/templates/core/dashboard.html` — tarjetas de ordenes abiertas/atrasadas.
- `backend/reports/views.py` — nuevo export `mantenimiento_excel`.
- `backend/reports/urls.py` — ruta `/reports/mantenimiento/excel/`.
- `backend/reports/templates/reports/index.html` — boton export mantenimiento.

*Ultima actualizacion: 2026-05-05 · Etapa 5E completada en repo*

---

## CRONOLOGIA COMPLETA (ORDENADA POR FECHA)

> Esta seccion resume todas las actualizaciones por fecha y mantiene el detalle original en sus secciones respectivas.

### 2026-05-04
- Etapa 3 (3A–3F) completa + patches documentados.
- Reconstruccion de entorno local y base Docker/Django.

### 2026-05-05
- Reports 4A/4B: tablero + PDF/Excel + costos/KPI.
- Mantenimiento 5A–5E: modelos, CRUD, templates, alertas, dashboard y export.
- Docker + migraciones para mantenimiento.

### 2026-05-06
- Reports (PDF inventario/usuarios) y ajustes de mantenimiento (repuestos/acciones).

### 2026-05-10
- Passwords 6A–6D: app base, CRUD, cifrado, acceso, export y logs.
- `.gitignore` + `entrypoint.sh` y Dockerfile actualizado para entrypoint.

---

## ACTUALIZACION 2026-05-18 — CAMBIOS IMPORTANTES

- Finalización de la Etapa 7 (Yule OCS Integration).
- Estabilización del módulo de Passwords.
- Limpieza de contenedores Docker y optimización de volúmenes.
- Documentación de procedimientos de respaldo (backup) y recuperación.

**Archivos actualizados:**
- `backend/yule/views.py` - lógicas de sincronización con OCS.
- `backend/passwords/utils.py` - mejoras en el cifrado.
- `docker-compose.yml` - ajustes en límites de memoria.

---

## AUDITORIA DE SEGURIDAD 2026-07-22

Auditoría exhaustiva realizada el 2026-07-22. Se aplicaron **10 cambios seguros** sin riesgo de romper funcionalidad existente. **7 hallazgos quedan pendientes** por riesgo de regresión.

### Cambios aplicados (seguros)

**Fase 1 — Settings**
- `SECRET_KEY`: ahora se genera aleatorio si no existe en `.env` (con log crítico). No rompe nada porque el `.env` real ya tiene el valor.
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = True` y `SESSION_COOKIE_AGE = 3600`: sesiones expiran al cerrar navegador y a 1 hora.
- `CSRF_TRUSTED_ORIGINS` ahora se puede configurar via `TRUSTED_ORIGINS` en `.env`. Defaults se mantienen.
- `PASSWORDS_ENCRYPTION_KEY`: warning si no está configurado (fallback sigue siendo SECRET_KEY).
- Configuración de logging de seguridad agregada (logger `security`).

**Fase 2 — Nginx**
- Headers de seguridad agregados a `nginx/nginx.conf`:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Referrer-Policy: strict-origin-when-cross-origin`

**Fase 3 — Rate limiting**
- Nuevo middleware `accounts/middleware.py` (`LoginRateLimitMiddleware`): limita a 5 intentos de login por minuto por IP. Sin dependencias externas. Agregado a `MIDDLEWARE` en settings.

**Fase 4 — Validación de archivos**
- `inventario/forms.py` (`SubirActaForm`): valida que el acta subida sea `.pdf`, `.jpg`, `.jpeg` o `.png`.
- `usuarios/forms.py` (`UsuarioForm`): valida que la foto sea `.jpg`, `.jpeg`, `.png`, `.gif` o `.webp`.

**Fase 5 — Mejoras menores**
- `yule/views.py` (`_mask_token`): tokens de 10 caracteres o menos ahora se enmascaran completamente (antes: 6).

### Preocupaciones pendientes (requieren evaluación de impacto)

Estos hallazgos **no se aplicaron** porque pueden romper funcionalidad existente. Se documentan aquí para revisión futura:

1. **Usuario no-root en Docker**: el `Dockerfile` actual ejecuta como root. Agregar `USER django-user` puede romper permisos en volúmenes montados (`./backend`, `static_volume` y el bind mount `./backend/media`). Requiere migración de permisos en el servidor (`chown -R 1000:1000 backend/media`).

2. **Content-Security-Policy (CSP)**: agregar CSP puede romper scripts inline y Bootstrap JS usados en templates. Requiere auditoría de todos los templates para ajustar nonces/policies.

3. **WeasyPrint `base_url=None`**: actualmente se usa `request.build_absolute_uri("/")` en `inventario/views.py:286` y `reports/views.py:202`. Cambiar a `None` puede romper la carga de imágenes/logo en PDFs generados.

4. **Validación MIME real con `python-magic`**: actualmente la validación es por extensión. Validar contenido real requiere agregar `python-magic` a `requirements.txt` (dependencia del sistema libmagic). No verificado en el entorno.

5. **Cambiar URL del admin (`/admin/`)**: cambiar a algo no obvio puede afectar accesos existentes y bookmarks de administradores.

6. **Reducir `client_max_body_size` en Nginx (de 50M)**: 50M puede ser excesivo, pero reducirlo puede romper uploads legítimos (actas escaneadas, fotos). Requiere definir tamaño máximo real necesario.

7. **Validación de `DEBUG` en producción**: actualmente `DEBUG` se lee de variable de entorno. Considerar solo permitir `DEBUG=True` cuando `ENVIRONMENT=development` explícitamente.

### Variables de entorno nuevas (opcionales)

Para aprovechar los cambios:
- `TRUSTED_ORIGINS`: lista separada por comas de origins CSRF de confianza para producción. Si no se define, se usan los defaults de desarrollo.
- `SECRET_KEY`: ya existía pero ahora su ausencia genera log crítico (en vez de usar valor inseguro).
- `PASSWORDS_ENCRYPTION_KEY`: ya existía pero ahora su ausencia genera warning (sigue funcionando con fallback).

*Auditoría completada 2026-07-22*

---

*Última actualización: 2026-09-09 · v1.1.0 + post-release importación masiva · Módulo documentos y mejoras de inventario integradas*
