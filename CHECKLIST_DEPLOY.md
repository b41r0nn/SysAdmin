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
# Servidor OCS en el MISMO host (192.168.1.250), puerto 8081.
# (8080/80/443 están ocupados o reservados; Hikvision usa 80/443.)
# Vista /yule/api/test-conexion/ y /yule/configuracion/ permiten
# validar la conexión sin tocar código.
# La URL debe terminar en /ocsapi/v1.
OCS_BASE_URL=http://192.168.1.250:8081/ocsapi/v1
OCS_USER=Administrador
OCS_TOKEN=<token_ocs>
OCS_VERIFY_SSL=False
```

> **⚠️ CRÍTICO — Vault de contraseñas:** `PASSWORDS_ENCRYPTION_KEY` debe ser una
> **clave Fernet válida de 44 caracteres** (`Fernet.generate_key()`), no una frase
> cualquiera. Si el valor existe pero no es una clave Fernet válida,
> `build_fernet()` (`passwords/crypto.py:15`) lanza
> `ValueError: Fernet key must be 32 url-safe base64-encoded bytes` y **nada se
> puede cifrar**: ni las credenciales del vault ni la contraseña de OCS en Yule
> (el formulario de configuración revienta en el `save()`).
> Si además `SECRET_KEY` falta, `base.py:15` genera una clave aleatoria **en cada
> arranque** (y distinta en cada worker de gunicorn) → sesiones perdidas en cada
> restart y descifrado intermitente del vault.
> Definir ambas claves ANTES del primer arranque, respaldarlas (el `backup.sh` ya
> incluye el `.env` en el paquete) y validar:
> ```bash
> docker exec sysadmin_django python -c 'import os,django;os.environ["DJANGO_SETTINGS_MODULE"]="sysadmin.settings.base";django.setup();from django.conf import settings;from passwords.crypto import build_fernet;build_fernet();print("FERNET_OK len:",len(settings.PASSWORDS_ENCRYPTION_KEY or ""),"| SK len:",len(settings.SECRET_KEY or ""))'
> ```
> Esperado: `FERNET_OK len: 44`.

## 3. Variables de contexto (código)

Claves que lee `settings/base.py`:

| Variable | Default | Se usa en |
|---|---|---|
| `SECRET_KEY` | random por arranque | sesiones, hash, cripto |
| `PASSWORDS_ENCRYPTION_KEY` | deriva de SECRET_KEY | vault (`passwords/crypto.py`) |
| `DJANGO_SETTINGS_MODULE` | `sysadmin.settings.local` (manage) / `sysadmin.settings.production` (wsgi) | Django |
| `DEBUG` | `False` | `README`, templates |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Django |
| `POSTGRES_DB/USER/PASSWORD` | — | compose + settings |
| `DB_HOST` | `db` | settings |
| `DB_PORT` | `5432` | settings |
| `SECURE_SSL_REDIRECT` | `True` en producción / `False` en local | HTTPS redirect Django |
| `SESSION_COOKIE_SECURE` | `True` en producción / `False` en local | cookies |
| `CSRF_COOKIE_SECURE` | `True` en producción / `False` en local | cookies |
| `SECURE_HSTS_SECONDS` | `31536000` en producción / `0` en local | HSTS |
| `TRUSTED_ORIGINS` | lista localhost + `https://192.168.1.250:6060` en prod | CSRF |
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

# 0. MEDIA_ROOT debe existir ANTES de levantar (bind mount ./backend/media).
#    Docker lo crearía como root y el contenedor corre como uid 1000.
mkdir -p backend/media && chmod 777 backend/media

# 1. Build con --no-cache (entorno WSL/mnt-c conocido por cachear mal)
docker compose build --no-cache django

# 2. Levantar
docker compose up -d

# 3. Verificación de salud
docker ps --filter name=sysadmin
# Esperar: db Healthy, django Healthy, nginx Started

# 4. Crear superusuario (si primera vez)
docker exec -it sysadmin_django python manage.py createsuperuser

# 5. Verificar que /app/media es la carpeta del host y no un volumen suelto
docker exec sysadmin_django sh -c 'touch /app/media/PRUEBA && ls -la /app/media'
ls -la backend/media && rm -f backend/media/PRUEBA
# Esperado: PRUEBA aparece en los dos listados
```

## 5. Validación post-deploy

- [ ] `https://192.168.1.250:6060/accounts/login/` → **200** (aceptar cert autofirmado).
- [ ] `http://192.168.1.250:6061/accounts/login/` → **301 Moved Permanently** hacia `https://...:6060`.
- [ ] Login OK → dashboard.
- [ ] Login erróneo ×5 → lockout (429) y registro `cuenta_bloqueada` en auditoría.
- [ ] `/admin/` accesible con cert aceptado.
- [ ] `docker exec sysadmin_django python manage.py check` → `0 issues`.
- [ ] `docker logs sysadmin_django --tail 20` → sin tracebacks.
- [ ] Documento subido desde la web se ve en el host: `ls -laR /opt/sysadmin/app/backend/media/documentos/`.
- [ ] Cortafuegos: desde otro PC, `telnet 192.168.1.250 6060` y `6061` responden; `8081/5432/22` no expuestos innecesariamente.

### Validación específica OCS (Yule)

- [ ] El servidor OCS responde en `http://192.168.1.250:8081/ocsreports` (200) y el login muestra el **menú completo**, no solo el logo.
      Si muestra solo el logo → falta el parche de `html_header.php` (ver `OCS_INVENTORY_SETUP.md`).
- [ ] API de OCS responde 200 con credenciales:
      `curl -s -o /dev/null -w '%{http_code}\n' -u '<OCS_USER>:<OCS_TOKEN>' -H 'ocs-apirequest: true' -H 'Accept: application/json' 'http://192.168.1.250:8081/ocsapi/v1/computers?limit=1'`
- [ ] Desde el contenedor Django alcanza OCS:
      `docker exec sysadmin_django python -c "import requests; print(requests.get('http://192.168.1.250:8081/ocsapi/v1/computers', timeout=5).status_code)"`
      → `200` (o `401` si aún no configura credenciales, pero **no** timeout/connection refused).
- [ ] En la UI: `https://192.168.1.250:6060/yule/api/test-conexion/` → `{"success": true}`.
- [ ] Si se configuró por `/yule/configuracion/`, verificar que la fila guardada sea la que aplica
      (prioridad BD sobre `.env`, ver sección 3).
- [ ] Sincronizar manual (`/yule/sincronizar/` o `docker exec sysadmin_django python manage.py sync_ocs`)
      y confirmar que `EquipoOCS` se llena y que el software snapshot llega a las hojas de vida.

### Validación específica del inventario de software (Fase 7B-bis)

- [ ] La migración está aplicada:
      `docker exec sysadmin_django python manage.py showmigrations inventario` → `0009_softwareinstalado [X]`.
- [ ] El sync simula sin escribir:
      `docker exec sysadmin_django python manage.py sincronizar_software --dry-run --verbose` → lista los activos **sin** "cambios".
- [ ] Sincronizar de verdad y comprobar que solo escribe diferencias:
      `docker exec sysadmin_django python manage.py sincronizar_software --verbose --pausa 2` → `Total en base: N filas`.
- [ ] Las dos páginas cargan (200): `/inventario/<pk>/software/` y `/inventario/software/`.
- [ ] El botón "Leer de OCS" de la ficha funciona (es lo único que golpea OCS).
- [ ] El cron quedó instalado y el log se escribe:
      `sudo grep sincronizar /etc/cron.d/sysadmin-sincronizar-software` · `tail -20 /var/log/sysadmin-software-sync.log`.
      Solo si se acaba de instalar: `sudo bash /opt/sysadmin/app/deploy/instalar_cron_software.sh`.
- [ ] Para esperar menos a la primera vuelta, correr el comando a mano **exactamente igual que el cron** (con sudo):
      `sudo docker exec sysadmin_django python manage.py sincronizar_software --verbose --pausa 2`.
- [ ] Un OCS caído **no** debe vaciar la base: apuntar la configuración a una URL inválida, correr el comando y verificar que el conteo no cambia.

## 6. Rollback

- El tag del commit desplegado (hoy `v2.4.0-2026-09-29`) es el punto de restauración git.
- Volumen `postgres_data` contiene la BD — respaldar antes de migrar (ver `setup_server.sh` → backup a NAS).
- Para rollback rápido:
  ```bash
  git checkout <tag-anterior> && docker compose up -d --build
  ```

## 7. Pendientes conocidos

- [ ] `DEBUG=True` en `.env` local de desarrollo (no usar en servidor).
- [ ] **OCS**: el servidor OCS (puerto 8081) es infraestructura independiente; si se expone
      fuera de la LAN, habilitar en UFW (`sudo ufw allow 8081/tcp`). OCS usa HTTP plano en LAN
      con `OCS_VERIFY_SSL=False` — no exponer fuera de la red interna sin TLS.
- [ ] **SOAP de OCS**: `Cannot find XML::Entities` — el paquete `libxml-entities-perl` no existe
      en Ubuntu 22.04. El agente SOAP no funciona; la web y la API JSON sí. No bloqueante para Yule.
- [ ] **Documentos**: los 2 PDFs de `documentos/2026/09/` están en el bind mount y
      `curl` a `https://192.168.1.250:6060/media/documentos/2026/09/<archivo>.pdf` devuelve 200.
- [ ] Renovar cert autofirmado (~dic 2028).
- [ ] Credenciales NAS para `backup.sh` (IP, usuario, ruta).