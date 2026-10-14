# Auditoría SysAdmin / REDIHOSSAS — 2026-10-14

**Repo:** `b41r0nn/SysAdmin` · commit auditado `7230125` (master) · solo lectura, nada modificado.
**Método:** clone + ejecución real de herramientas (Python 3.11, deps de `requirements.txt`): `pip-audit`, `bandit`, `ruff`, `radon`, `vulture`, `manage.py check --deploy`, `makemigrations --check`, suite de tests con `coverage`, más lectura de código/infra. Cada hallazgo lleva evidencia `archivo:línea`. Lo no verificado en servidor real está marcado.

## Resumen

| Área | Estado |
|---|---|
| Tests | **405/406** (1 falla real). Cobertura global 76 % |
| Migraciones | Sincronizadas (`No changes detected`) |
| `check --deploy` | 1 warning (HSTS; nginx lo envía — intencional) |
| Bandit | 0 High, 2 Medium (falso positivo/aceptable), 3 Low |
| Vistas sin auth | Solo 2, ambas intencionales (QR público, form soporte público) |
| Dependencias | **Django 4.2 EOL + CVEs en 7 de 16 paquetes** |
| Lint | 280 hallazgos ruff, sin config de lint, sin lint en CI |

Base sólida para app LAN: auth + permisos por rol en todas las vistas, axes, validadores, Fernet para secretos, sin SQL crudo, sin `csrf_exempt`, sin `|safe`. Los problemas reales están en: dependencias, `/media/` sin auth, sesión de 3 min, atomicidad, y operación (backup/Docker/CI).

---

## 🔴 Alto

### A1. Django 4.2.13 sin soporte + CVEs en dependencias
`requirements.txt` — `pip-audit` (verificado):

| Paquete | Versión | Vulns | Corrige en |
|---|---|---|---|
| Django | 4.2.13 | 44 | 4.2.30 (último 4.2; **4.2 llegó a EOL abr-2026**) → migrar a **5.2.17 LTS** |
| Pillow | 10.3.0 | 17 | 12.3.0 |
| cryptography | 42.0.8 | 7 | 49.0.0 |
| WeasyPrint | 60.2 | 4 | 70.0 |
| gunicorn | 21.2.0 | 2 (request smuggling) | 22.0.0 |
| requests | 2.32.3 | 2 | 2.33.0 |
| python-dotenv | 1.0.1 | 1 | 1.2.2 |

Sin exposición a internet baja el riesgo, pero Pillow/WeasyPrint procesan archivos subidos y 4.2 ya no recibe parches. **Fix:** subir a 4.2.30 ya (cambio mínimo, mismo mayor) y planear 5.2 LTS (soporte hasta 2028) con la suite como red. WeasyPrint 60→70 cambia API: probar PDFs a mano (PosixPath bug previo).

### A2. nginx sirve `/media/` sin autenticación
`nginx/nginx.conf:46-48` (`location /media/ { alias /app/media/; }`).
Archivos en `/media/`: actas firmadas (`inventario/actas/firmadas/`), PDFs de actas, `documentos/%Y/%m/`, fotos de usuarios (`models.py` de inventario:295-297, documentos:43, usuarios:21).
Las vistas `ver_documento`/`descargar_documento` (documentos/views.py:96-113) validan permiso, pero **cualquiera en la LAN con la URL baja el archivo sin login**, saltándose roles. Nombres = nombre original del archivo → adivinables.
**Fix:** `location /media/ { internal; }` + servir vía Django con `X-Accel-Redirect` (o `FileResponse` tras `requiere_permiso`). Mínimo: bloquear `/media/inventario/actas/` y `/media/documentos/`.

### A3. Sesión de 3 minutos absolutos (no por inactividad) + CI en rojo
`backend/sysadmin/settings/base.py:139` `SESSION_COOKIE_AGE = 180  # 3 minutos (inactividad)` (commit `b9c8541`, 1-oct).
**Verificado empíricamente:** login → 3 requests posteriores → `expire_date` **no cambia**. Sin `SESSION_SAVE_EVERY_REQUEST = True` el timeout cuenta desde el login, no desde la última actividad: el usuario es expulsado a los 3 min aunque esté trabajando.
Además `accounts/tests.py:222` aún asserta `28800` → **`test_cookies_sesion_seguras` falla** (405/406), y la doc (`FASES.md:391`, `docs/sesiones/SESION_2026-09-24_RESUMEN.md:74`) sigue diciendo 8 h.
**Fix:** decidir el valor (3 min es muy corto para formularios largos/actas; 15-30 min típico), añadir `SESSION_SAVE_EVERY_REQUEST = True`, actualizar test y docs.

---

## 🟠 Medio

### M1. Escrituras multi-paso sin transacción (1 solo `@transaction.atomic` en todo el repo)
Único uso: `inventario/software_sync.py:57`.
- `asignar_activo` (inventario/views.py:289-326): `Asignacion.save` → `Movimiento.create` → `ActaAsignacion.create` → `encolar_email` → `activo.estado="asignado"`. Si falla algo a mitad (p. ej. encolar email), queda asignación activa con activo "disponible". Sin `select_for_update`: dos técnicos simultáneos pueden asignar el mismo activo (la validación `estado != "disponible"` no es atómica).
- `devolver_activo` (356-384), `trasladar_activo`, `confirmar_importar_activos` (1036-1085): mismo patrón; `confirmar_importar_usuarios` (usuarios/views.py:143) no revisado línea a línea. El import usa `except Exception` por fila y cuenta "error" — un `IntegrityError` real queda mudo.
- `Activo._siguiente_numero_interno` (inventario/models.py:37-40) = `Max()+1` → carrera → `IntegrityError` (unique) silenciado en import.
- `activo.save()` sin `update_fields` (varias vistas) puede pisar cambios concurrentes (p. ej. sync OCS).
**Fix:** `@transaction.atomic` + `select_for_update()` en asignar/devolver/trasladar; reintento o secuencia DB para `numero_interno`; loguear la excepción en import.

### M2. Axes detrás de nginx: IP = contenedor nginx; auditoría con IP falsificable
- `django-ipware` **no está instalado** (no está en `requirements.txt`), así que axes cae a `request.META['REMOTE_ADDR']` (axes/helpers.py:`get_client_ip_address`) = IP del contenedor nginx para todos. Con `LOCKOUT_PARAMETERS=[["username","ip_address"]]` el bloqueo efectivo es **por usuario**: cualquiera en la LAN puede bloquear 1 h la cuenta del superadmin con 5 intentos.
- `accounts/signals.py:8-14` y `administracion/signals.py:10` toman el **primer** hop de `X-Forwarded-For`; nginx usa `$proxy_add_x_forwarded_for` (nginx.conf:30) que **conserva lo que mande el cliente** → IP de auditoría falsificable, e inconsistente con la de axes.
**Fix:** nginx `proxy_set_header X-Forwarded-For $remote_addr;` + función única `get_client_ip` (último hop de XFF) usada por axes vía `AXES_CLIENT_IP_CALLABLE` y por las señales de auditoría. (Ojo: `AXES_IPWARE_*` no sirve sin ipware instalado.)

### M3. Formulario público de soporte: cooldown evadible
`soporte/views.py:50-67` el cooldown vive en la sesión; cliente sin cookies (curl/script) nunca lo activa (`session_key` vacío → `False`). Cada ticket notifica a **todos** los usuarios TI (`_notificar_ti_ticket`, 35-37). nginx no tiene `limit_req`. Honeypot solo frena bots tontos.
**Fix:** `limit_req_zone` en nginx para `/soporte/reportar-publico/` y/o cooldown por IP en caché/BD.

### M4. Clave del vault con fallback a `SECRET_KEY` + backup junta clave y datos
- `passwords/crypto.py:9-13`: sin `PASSWORDS_ENCRYPTION_KEY` deriva la clave de `SECRET_KEY`. `production.py` no lo exige. Rotar `SECRET_KEY` deja ilegibles vault y contraseñas SMTP/OCS (`administracion/models.py:62`) sin aviso.
- `setup_server.sh` (backup): mete `pg_dumpall` **y `.env` (clave de cifrado)** en el mismo `.tar.gz` enviado al NAS → quien lea el NAS descifra todo el vault.
**Fix:** `ImproperlyConfigured` en producción si falta la clave; backup de `.env` separado/cifrado (o solo guardar la clave aparte).

### M5. UI depende de CDNs externos, sin SRI (app 100 % LAN)
`templates/base.html:9-19,155` (jsdelivr bootstrap + icons, Google Fonts, **unpkg htmx**), y también `qr_publico.html`, `calendario.html`, `reporte_publico*.html`. 0 atributos `integrity=`.
Servidor/LAN sin internet ⇒ UI sin estilos ni HTMX; con internet, cadena de suministro sin verificación (unpkg).
**Fix:** vendorizar Bootstrap/Icons/htmx/fuentes en `backend/static/` (o al menos SRI + versión fija).

### M6. Backup: fallos silenciosos y sin retención real
`setup_server.sh` (script de backup): `tar … 2>/dev/null || true` oculta fallos; `rsync -az --delete` espeja el directorio local → al borrar locales >7 días se borran también en el NAS (**sin historial**); variables NAS con placeholders (`192.168.1.XXX`); dump SQL en claro en disco; nunca probado restore. Cron solo se instala si corrió `setup_server.sh` (pendiente conocido).
**Fix:** quitar `|| true` y `set -euo pipefail`; rsync sin `--delete` (retención en NAS); probar restore; verificar que el cron exista en el servidor real.

### M7. Docker/gunicorn
- `backend/Dockerfile`: corre como **root**, sin `USER`; sin `.dockerignore`.
- `backend/entrypoint.sh:8`: `gunicorn` con defaults = **1 worker sync, timeout 30 s**. Un PDF WeasyPrint largo bloquea toda la app y puede morir por timeout. Usar `--workers 3 --timeout 120`.
- `docker-compose.yml:30`: `./backend:/app` — el contenedor ejecuta el código del host (de ahí los 777). `setup_server.sh:113`: `chmod 777 …/media`.
- `migrate` + `collectstatic` en cada arranque (aceptable en instancia única).

### M8. CI incompleto y desalineado con producción
`.github/workflows/ci.yml`: tests sobre **SQLite**, prod es PostgreSQL 15; sin lint, sin `pip-audit`, sin `makemigrations --check`, sin `check --deploy`, sin cobertura. Hoy **está en rojo** (A3).

---

## 🟡 Bajo

- **L1 · Calidad:** ruff (reglas por defecto de 0.17): 280 hallazgos, 151 autofijables. No-test: ~17 `F401` (imports sin uso; `login_required` sobrante en 4 views), 23 `E741` (variable `l` en `licencias/views.py:26-243`), 16 `BLE001` (`except Exception`), 2 `S110` (`try/except/pass`: inventario/views.py:926, notificaciones/services.py:319), 4 `B904`. Sin `pyproject.toml`/`ruff.toml`/formatter.
- **L2 · Complejidad (radon):** `reports.views.inventario_pdf` CC 34, `inventario_excel` 26, `inventario.software_sync.aplicar_reporte` 32, `soporte.views.tickets_excel` 21. Archivos grandes: `inventario/views.py` 1290 líneas, `reports/views.py` 1104.
- **L3 · Cobertura baja en lo sensible:** `inventario/views.py` **33 %** (545 stmts), `usuarios/views.py` 52 %, `yule/admin.py` 54 %, `yule/client.py` 63 %. Management commands **0 %**: `limpiar_historial` (82 stmts, borra datos), `sync_ocs`, comandos de notificaciones; `settings/production.py` 0 %.
- **L4 · BOM UTF-8:** `accounts/signals.py` y `patch_ocs_server.sh` (el BOM antes de `#!` rompe ejecución directa del script; también hace fallar `radon`).
- **L5 · nginx:** sin CSP; `static/` y `media/` no llevan `X-Content-Type-Options`/`X-Frame-Options` (el comentario asume que los pone Django, pero esas rutas no pasan por Django); un HTML subido a `/media/` se ejecuta en el origen de la app. `HSTS includeSubDomains` sobre una IP con cert autofirmado no aporta. Redirect con `:6060` hardcodeado. Sin gzip.
- **L6 · QR público:** `/inventario/<pk>/qr/publico/` enumerable por pk secuencial; expone serial, marca/modelo, tipo, nº interno (sin datos de personas — verificado en `qr_publico.html`). Aceptable en LAN; considerar token en vez de pk.
- **L7 · Acoplamiento:** `soporte/views.py` importa helpers privados (`_apply_redihos_*`) de `reports.views`; mover a módulo común (`core/excel.py`).
- **L8 · `mark_safe`** (`reports/views.py:564`): usa `activo.estado` (choices) y texto de display; sin entrada de usuario → falso positivo, pero preferible `format_html`.
- **L9 · Docs:** 7 informes `.md` en la raíz (SYSADMIN_HANDOFF.md 93 KB); alguna doc contradice el código (sesión 8 h vs 3 min). Mover a `docs/`.

## Pendientes tuyos confirmados por el código
- **Import masivo de activos** (duda abierta): matchea contra **`CAMPOS_IMPORTABLES`** (`inventario/views.py:853`), *no* `CAMPOS_LICENCIAS` ni `CAMPOS_INVENTARIO`. Dedupe por `serial`, en dos pasadas (preview + confirmación). Sin transacción (ver M1).
- SMTP, NAS, rotar `rootpass` OCS, etc.: siguen fuera del repo (operación).

## Orden sugerido
1. **A3** (5 min): `SESSION_COOKIE_AGE` razonable + `SESSION_SAVE_EVERY_REQUEST=True` + test → CI verde.
2. **A2**: cerrar `/media/` (impacto real en datos personales).
3. **A1**: Django 4.2.30 + gunicorn 22 + Pillow/requests/cryptography ahora; Django 5.2 LTS como tarea aparte.
4. **M1** atomicidad en asignar/devolver/trasladar/import.
5. **M2/M3** nginx (`X-Forwarded-For`, `limit_req`) + config axes.
6. **M5** vendorizar CDNs.
7. **M6/M7/M8** backup, gunicorn workers + no-root, CI con lint/pip-audit/migrations check.
8. Limpieza L1-L9 (`ruff --fix` cubre ~150).

## Verificado como correcto
Auth en todas las vistas salvo 2 públicas intencionales · `@requiere_permiso` con bypass solo superuser · `solo_superadmin` bien definido · CSRF activo, sin `csrf_exempt` · sin `|safe` ni SQL crudo · cookies HttpOnly/SameSite · validadores de contraseña (min 10) · axes con mensajes genéricos · Fernet para secretos · `.env`/certs/dumps en `.gitignore` y no versionados · `DEBUG=False` forzado en `production.py` · `SECRET_KEY` obligatoria en producción · PostgreSQL sin puerto expuesto · healthchecks y `depends_on` correctos · migraciones consistentes · 406 tests, 405 pasan.
