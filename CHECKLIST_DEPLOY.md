# Checklist de Deploy — SysAdmin

Runbook de referencia para desplegar SysAdmin en el servidor (`192.168.1.250`).
Leer junto con `README.md`, `SYSADMIN_HANDOFF.md` y `setup_server.sh`.

---

## 1. Pre-requisitos

- [ ] Servidor Ubuntu con `setup_server.sh` ejecutado (instala Docker, UFW con puertos `22`, `6060`, `6061`, y genera el cert autofirmado en `/opt/sysadmin/app/nginx/certs/`).
- [ ] Proyecto copiado en `/opt/sysadmin/app` (por rsync o `git clone`).
- [ ] Cert autofirmado presente en `nginx/certs/server.crt` + `server.key` (nunca vía git — se genera en el servidor).
- [ ] UFW activo: `sudo ufw status numbered` debe listar `22/tcp`, `6060/tcp`, `6061/tcp`.

## 2. Archivo `.env` de producción

El `.env` NO se versiona. Copiar `.env.example` (o el `.env` de desarrollo) y ajustar:

```ini
# ── Obligatorios ───────────────────────────────────────────────
SECRET_KEY=generar:  python -c "import secrets; print(secrets.token_urlsafe(50))"
PASSWORDS_ENCRYPTION_KEY=generar:  python -c "import secrets; print(secrets.token_urlsafe(50))"
DEBUG=False
ALLOWED_HOSTS=192.168.1.250,localhost,127.0.0.1

# ── Base de datos ──────────────────────────────────────────────
POSTGRES_DB=sysadmin
POSTGRES_USER=sysadmin_user
POSTGRES_PASSWORD=<fuerte>
DB_HOST=db
DB_PORT=5432

# ── Seguridad HTTP (HTTPS detrás de nginx) ─────────────────────
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
TRUSTED_ORIGINS=https://192.168.1.250:6060,https://localhost:6060

# ── OCS (Yule) ─────────────────────────────────────────────────
# Servidor OCS en el MISMO host (192.168.1.250), puerto 8080.
# Vista /yule/api/test-conexion/ y /yule/configuracion/ permiten
# validar la conexión sin tocar código.
OCS_BASE_URL=http://192.168.1.250:8080
OCS_USER=<usuario_ocs>
OCS_TOKEN=<token_ocs>
OCS_VERIFY_SSL=False
```

> **⚠️ CRÍTICO — Vault de contraseñas:** si falta `PASSWORDS_ENCRYPTION_KEY`, el vault
> (`passwords/crypto.py`) deriva la clave de `SECRET_KEY`. Si `SECRET_KEY` tampoco está
> configurado, se genera **una distinta en cada arranque** y las credenciales guardadas
> en el vault quedan **ilegibles para siempre**. Definir ambas claves ANTES del primer
> arranque y respaldarlas.

## 3. Variables de contexto (código)

Claves que lee `settings/base.py`:

| Variable | Default | Se usa en |
|---|---|---|
| `SECRET_KEY` | random por arranque | sesiones, hash, cripto |
| `PASSWORDS_ENCRYPTION_KEY` | deriva de SECRET_KEY | vault (`passwords/crypto.py`) |
| `DEBUG` | `False` | `README`, templates |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Django |
| `POSTGRES_DB/USER/PASSWORD` | — | compose + settings |
| `DB_HOST` | `db` | settings |
| `DB_PORT` | `5432` | settings |
| `SECURE_SSL_REDIRECT` | `False` | HTTPS redirect Django |
| `SESSION_COOKIE_SECURE` | `False` | cookies |
| `CSRF_COOKIE_SECURE` | `False` | cookies |
| `SECURE_HSTS_SECONDS` | `31536000` (o `0` si DEBUG) | HSTS |
| `TRUSTED_ORIGINS` | lista localhost | CSRF |
| `OCS_BASE_URL` | `''` | yule |
| `OCS_USER` / `OCS_TOKEN` | `''` | yule |
| `OCS_VERIFY_SSL` | `True` | yule |

> **IMPORTANTE — OCS tiene prioridad en BD:** `backend/yule/client.py::build_client()`
> usa **primero** la fila `ConfiguracionYule` activa guardada desde `/yule/configuracion/`
> (URL + usuario + password en BD). El `.env` (`OCS_BASE_URL`, `OCS_USER`, `OCS_TOKEN`)
> es solo el **fallback** si NO existe configuración en BD. Si deployás con valores
> viejos en la BD de producción, los del `.env` serán ignorados. Revisar por UI tras
> el deploy.

## 4. Deploy

```bash
cd /opt/sysadmin/app

# 1. Build con --no-cache (entorno WSL/mnt-c conocido por cachear mal)
docker compose build --no-cache django

# 2. Levantar
docker compose up -d

# 3. Verificación de salud
docker ps --filter name=sysadmin
# Esperar: db Healthy, django Healthy, nginx Started

# 4. Crear superusuario (si primera vez)
docker exec -it sysadmin_django python manage.py createsuperuser
```

## 5. Validación post-deploy

- [ ] `https://192.168.1.250:6060/accounts/login/` → **200** (aceptar cert autofirmado).
- [ ] `http://192.168.1.250:6061/accounts/login/` → **301 Moved Permanently** hacia `https://...:6060`.
- [ ] Login OK → dashboard.
- [ ] Login erróneo ×5 → lockout (429) y registro `cuenta_bloqueada` en auditoría.
- [ ] `/admin/` accesible con cert aceptado.
- [ ] `docker exec sysadmin_django python manage.py check` → `0 issues`.
- [ ] `docker logs sysadmin_django --tail 20` → sin tracebacks.
- [ ] Cortafuegos: desde otro PC, `telnet 192.168.1.250 6060` y `6061` responden; `8080/5432/22` no expuestos innecesariamente.

### Validación específica OCS (Yule)

- [ ] El servidor OCS responde en `http://192.168.1.250:8080/ocsreports` (asistente OK).
- [ ] Desde el contenedor Django alcanza OCS:
      `docker exec sysadmin_django python -c "import requests; print(requests.get('http://192.168.1.250:8080/ocsapi/v1/computers', timeout=5).status_code)"`
      → `200` (o `401` si aún no configura credenciales, pero **no** timeout/connection refused).
- [ ] En la UI: `https://192.168.1.250:6060/yule/api/test-conexion/` → `{"success": true}`.
- [ ] Si se configuró por `/yule/configuracion/`, verificar que la fila guardada sea la que aplica
      (prioridad BD sobre `.env`, ver sección 3).
- [ ] Sincronizar manual (`/yule/sincronizar/` o `docker exec sysadmin_django python manage.py sync_ocs`)
      y confirmar que `EquipoOCS` se llena y que el software snapshot llega a las hojas de vida.

## 6. Rollback

- El tag `v2.3.0-2026-09-24` (o el tag del commit desplegado) es el punto de restauración git.
- Volumen `postgres_data` contiene la BD — respaldar antes de migrar (ver `setup_server.sh` → backup a NAS).
- Para rollback rápido:
  ```bash
  git checkout <tag-anterior> && docker compose up -d --build
  ```

## 7. Pendientes conocidos

- [ ] `DEBUG=True` en `.env` local de desarrollo (no usar en servidor).
- [ ] **OCS**: el servidor OCS (puerto 8080) es infraestructura independiente; si se expone
      fuera de la LAN, habilitar en UFW (`sudo ufw allow 8080/tcp`). OCS usa HTTP plano en LAN
      con `OCS_VERIFY_SSL=False` — no exponer fuera de la red interna sin TLS.
- [ ] Renovar cert autofirmado (~dic 2028).
- [ ] Credenciales NAS para `backup.sh` (IP, usuario, ruta).