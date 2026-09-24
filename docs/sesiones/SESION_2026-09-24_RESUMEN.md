# Resumen de Sesión · 24 de septiembre de 2026

**Fecha:** 24 de septiembre de 2026
**Versión:** v1.10.0 (seguridad del login + HTTPS interno)
**Estado:** Endurecimiento de seguridad solicitado por el arquitecto (7 tareas) + login de reportar falla en nueva pestaña · **313/313 tests OK**
**Commits:** 1 realizado (login en nueva pestaña) — el endurecimiento de seguridad queda **en el working tree, SIN commitear** (revisión del arquitecto)

---

## 1. Motivo de la sesión

El usuario pidió dos cosas:

1. Que el enlace "Reportá una falla" del login abra el módulo `/soporte/reportar-publico/` **en una ventana aparte**.
2. (Después) Aplicar las **7 tareas de seguridad** indicadas por el arquitecto sobre el login y la infraestructura.

---

## 2. Implementación

### 2.1 Login — "Reportar una falla" en nueva pestaña

| Archivo | Cambio |
|---------|--------|
| `accounts/templates/accounts/login.html` | Enlace a `soporte:reportar_publico` con `target="_blank" rel="noopener"` |

### 2.2 Task 1 — Rate limit / lockout con django-axes

Se reemplazó el middleware custom `accounts.middleware.LoginRateLimitMiddleware` (en memoria) por **django-axes 8.3.1** (persistente en BD).

| Archivo | Cambio |
|---------|--------|
| `requirements.txt` (raíz) | `django-axes==8.3.1` agregada |
| `sysadmin/settings/base.py` | `axes` en `INSTALLED_APPS`; eliminado `accounts.middleware.LoginRateLimitMiddleware`; `axes.middleware.AxesMiddleware` al final de `MIDDLEWARE`; `AXES_FAILURE_LIMIT=5`, `AXES_COOLOFF_TIME=1` (hora), `AXES_LOCKOUT_PARAMETERS=[["username","ip_address"]]`, `AXES_RESET_ON_SUCCESS=True`; mensajes de lockout genéricos |
| `accounts/middleware.py` (eliminado) | Reemplazado por axes |

- Backends: `AUTHENTICATION_BACKENDS = ["axes.backends.AxesStandaloneBackend", "django.contrib.auth.backends.ModelBackend"]`.
- Migraciones de axes aplicadas en dev (`migrate`, sin migraciones propias del proyecto).
- Validado: bloqueo real tras el 5.º intento fallido → HTTP **429**.

### 2.3 Task 2 — Mensajes de error genéricos

| Archivo | Cambio |
|---------|--------|
| `accounts/forms.py` (nuevo) | `SysAdminAuthenticationForm(AuthenticationForm)`: `invalid_login` = "Usuario o contraseña incorrectos." (mismo mensaje para usuario inexistente o clave errónea, sin revelar existencia); `inactive` = "Esta cuenta está inactiva. Contacte al administrador." |
| `accounts/urls.py` | `LoginView` usa `authentication_form=SysAdminAuthenticationForm` |

### 2.4 Task 3 — Log de intentos fallidos en `RegistroAuditoria`

| Archivo | Cambio |
|---------|--------|
| `accounts/signals.py` (nuevo) | En `user_login_failed` → `registrar_auditoria(modulo="auth", accion="login_fallido", detalle="Intento de inicio de sesión fallido para el usuario '<username>'.")`. En `axes.signals.user_locked_out` → `accion="cuenta_bloqueada"` con usuario + IP bloqueante. Soporta `HTTP_X_FORWARDED_FOR` (primer hop) para el IP detrás de nginx. |
| `accounts/apps.py` | `ready()` importa `accounts.signals` |

### 2.5 Task 4 — Password validators

| Archivo | Cambio |
|---------|--------|
| `sysadmin/settings/base.py` | `AUTH_PASSWORD_VALIDATORS`: `MinimumLengthValidator(min_length=10)`, `UserAttributeSimilarityValidator`, `CommonPasswordValidator`, `NumericPasswordValidator` |

### 2.6 Task 5 — Headers de seguridad nativos

| Archivo | Cambio |
|---------|--------|
| `sysadmin/settings/base.py` | `SECURE_CONTENT_TYPE_NOSNIFF=True`, `X_FRAME_OPTIONS="DENY"`, `SECURE_REFERRER_POLICY="same-origin"` |

- El `SecurityMiddleware` ya estaba en `MIDDLEWARE` (posición 0). Headers verificados en runtime real.
- Nginx agrega además `X-XSS-Protection` y `Referrer-Policy` a nivel de proxy (doble capa).

### 2.7 Task 6 — Cookies de sesión seguras

| Archivo | Cambio |
|---------|--------|
| `sysadmin/settings/base.py` | `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"`, `SESSION_COOKIE_AGE=28800` (8 h), `SESSION_EXPIRE_AT_BROWSER_CLOSE=True` |

- `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` y `SECURE_SSL_REDIRECT` siguen por `env` (default `False`) mientras no se fuerce HTTPS en producción (ver §4).

### 2.8 Task 7 — HTTPS interno LAN (nginx + cert autofirmado)

| Archivo | Cambio |
|---------|--------|
| `nginx/certs/server.crt` + `server.key` (nuevos, untracked) | Cert autofirmado CN=192.168.1.250, 825 días (válido Sep 24 2026 → Dec 27 2028), generado con OpenSSL de Git (`C:\Program Files\Git\usr\bin\openssl.exe`) |
| `nginx/nginx.conf` | Server 80 → `return 301 https://$host$request_uri`; server 443 ssl con los certs + headers de seguridad; proxy a `django:8000` con `X-Forwarded-Proto`; aliases static/media |
| `docker-compose.yml` | Puertos nginx: `6060:443` (HTTPS) y `6061:80` (HTTP → redirect); volumen `./nginx/certs:/etc/nginx/certs:ro` |
| `sysadmin/settings/base.py` | CSRF trusted origins default incluye `https://localhost:6060` y `https://192.168.1.250:6060` |
| `.env` (no versionado) | `TRUSTED_ORIGINS=https://192.168.1.250:6060,https://localhost:6060` (antes http) |

> ⚠️ El cert autofirmado genera warning en el navegador (esperable en LAN). No probado en vivo: requiere Docker corriendo (§4).

### 2.9 Tests

| Archivo | Cambio |
|---------|--------|
| `accounts/tests.py` | Nueva clase `LoginSeguridadTests` (~11 tests): mensaje genérico, no revela existencia del usuario, 5 fallos registrados en BD, bloqueo → 429, auditoría `login_fallido`/`cuenta_bloqueada`, login exitoso resetea contador (0), cookies de sesión, headers presentes, config axes activa, password validators (min 10) |
| `administracion/tests.py` | Tests de señal login/logout migrados a `force_login` (axes exige request en `authenticate`) |
| `soporte/tests.py` | `test_reportar_falla_no_aparece_en_nav_autenticado` con `force_login` |

- `force_login` emite `user_logged_in`, por lo que los tests de auditoría siguen pasando.

---

## 3. Verificación

| Check | Resultado |
|-------|-----------|
| `manage.py check` | ✅ 0 issues |
| `makemigrations --check` | ✅ No changes detected |
| `accounts` tests | ✅ 22/22 OK |
| Suite completa | ✅ **313/313 OK** (302 existentes + 11 nuevos) |
| Bloqueo runtime (runserver real, POSTs con CSRF) | ✅ POST 1-4 = 200, **POST 5 = 429**, POST 6 = 429 (bloqueo al 5.º fallo) |
| Reset por éxito (runtime real) | ✅ `AccessAttempt validacion_seg tras exito: 0` |
| Auditoría en `RegistroAuditoria` (modulo `auth`) | ✅ `login_fallido` (6) y `cuenta_bloqueada` (2) con IP |
| Headers en runtime (`/accounts/login/`) | ✅ `X-Content-Type-Options: nosniff` · `X-Frame-Options: DENY` · `Referrer-Policy: same-origin` |
| HTTPS en vivo (https 200 / http 301) | ⏳ Pendiente — requiere levantar Docker (§4) |

---

## 4. Notas técnicas / pendientes de entorno

- **HTTPS pendiente de validar en vivo:** Docker Desktop no está corriendo en esta máquina. Para validar el mapeo https/http:
  `docker compose up -d --build`, luego https://192.168.1.250:6060 (base 200, con warning de cert autofirmado) y http://192.168.1.250:6061 → redirect 301 a https.
- **Requisitos duplicados:** `requirements.txt` (raíz, versión Docker) y `backend/requirements.txt` conviven; la dependencia nueva `django-axes==8.3.1` se agregó al de la raíz. `requirements.txt` local requiere `pip install` antes de correr tests si no se reinstaló.
- **`SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`:** siguen en `False` por default (configurables por env). La cookie de sesión se envía por HTTPS una vez desplegado sobre https. Re-evaluar antes de producción.
- **Axes y proxies:** nginx envía `X-Forwarded-For`; el IP bloqueante capturado usa el primer hop (patrón habitual tras proxy reverso).
- **Reset del contador:** `AXES_RESET_ON_SUCCESS=True` — un login exitoso limpia los fallos acumulados del usuario (verificado en runtime).
- **Cert autofirmado:** vigencia 825 días comienza el 24-sep-2026. Anotar renovación (~fines de 2028) en el checklist de infra.
- **BD local:** los intentos de prueba dejaron registros `auth/login_fallido` y `auth/cuenta_bloqueada` en la `db.sqlite3` de dev (no versionada).

---

## 5. Próximos pasos sugeridos

1. **Revisión del arquitecto del diff sin commitear** (10 archivos modificados, 1 eliminado, 3 untracked — ver §6).
2. Levantar Docker en el servidor y validar https:// y el redirect 301.
3. Decidir si se fuerzan `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE=True` por `.env` en producción con HTTPS.
4. Actualizar accesos del README internos/SOP de http → https (ver §7).
5. Fijar recordatorio de renovación del cert autofirmado.

---

## 6. Estado del working tree

**Commit realizado (login nueva pestaña):**

| Commit | Contenido |
|--------|-----------|
| `26d0a6d` | feat: login page template — apertura de "reportar falla" en pestaña nueva (`target="_blank"`) |

**Sin commitear (seguridad, para revisión del arquitecto):**
- Modificados: `sysadmin/settings/base.py`, `accounts/apps.py`, `accounts/urls.py`, `accounts/tests.py`, `administracion/tests.py`, `soporte/tests.py`, `docker-compose.yml`, `nginx/nginx.conf`, `requirements.txt`
- Eliminado: `accounts/middleware.py`
- Nuevos: `accounts/forms.py`, `accounts/signals.py`, `nginx/certs/server.crt` + `server.key`

---

## 7. Documentación actualizada en esta sesión

- `SESION_2026-09-24_RESUMEN.md` (este archivo)
- `README.md` — estado, acceso HTTPS, changelog v1.10.0
- `SYSADMIN_HANDOFF.md` — estado actual + changelog de seguridad
- `FASES.md` — FASE 7: Seguridad del login + HTTPS

---

**Preparado por:** Asistente SysAdmin
**Fecha de cierre:** 24 de septiembre de 2026