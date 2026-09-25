# SysAdmin · Runbook operativo de producción

> Estado al **2026-09-25**. Referencia compacta para el arqui/agente.
> El histórico detallado vive en `SYSADMIN_HANDOFF.md`; OCS tiene su propio
> doc en `OCS_INVENTORY_SETUP.md`.

## Ambiente

- Servidor: `sistemas@192.168.1.250` · Ubuntu Server 22.04 · proyecto en `/opt/sysadmin/app` (Docker Compose).
- Web: `https://192.168.1.250:6060` (HTTPS) · `http://192.168.1.250:6061` (301 → https). Cert autofirmado CN=192.168.1.250.
- Contenedores: `sysadmin_db` (postgres:15-alpine) · `sysadmin_django` (django 4.2 / python 3.11, gunicorn, axes) · `sysadmin_nginx`. Hikvision corre aparte en sus propios contenedores/redes y **ocupa los puertos 80/443 del host** (no se toca).
- OCS Inventory NG: `http://192.168.1.250:8081/ocsreports/` (contenedores `ocsinventory-db` / `ocsinventory-server`; el `ocsinventory-proxy` está detenido a propósito).
- `.env` en `/opt/sysadmin/app/.env` (`DEBUG=False`). Repo local = fuente · servidor = copia vía `rsync` (excluye `venv/`, `backend/media/`, `tmp_scratch*`).

## Accesos

- Admin Django: `https://192.168.1.250:6060/accounts/login/` (login = `accounts.CustomUser`; superusuarios creados en deploy).
- Consola: `docker exec -it sysadmin_django python manage.py shell`.
- DB: `docker exec -it sysadmin_db psql -U sysadmin_user -d sysadmin_db`.
- Credenciales de BD en producción: base `sysadmin`, usuario `sysadmin_user`, pass en `/opt/sysadmin/app/.env`.

## Archivos subidos (MEDIA_ROOT) — fix crítico aplicado

`MEDIA_ROOT = BASE_DIR/'media'` (`base.py:166`) y en el contenedor eso es
`/app/media`. El compose lo monta como **bind mount** a `./backend/media`:

```yaml
# django
- ./backend/media:/app/media
# nginx (sirve /media/ con alias, nginx.conf:40-42)
- ./backend/media:/app/media
```

**Por qué importa:** con el volumen con nombre que se usó en el primer deploy
(`media_volume:/app/media`), todo archivo subido por la web quedaba dentro de
`/var/lib/docker/volumes/...`, invisible desde el host, sin posibilidad de
respaldar, y `rsync` (que excluye `backend/media/`) nunca lo copiaba. Efecto
observado: los documentos existían en la BD pero "ver" daba error porque el
archivo no estaba.

Reglas:

- **Ambos servicios** (django y nginx) deben apuntar al mismo bind mount, o
  Django sube el archivo y nginx no lo sirve.
- El directorio se crea antes de `docker compose up -d`, con permisos abiertos:
  ```bash
  mkdir -p /opt/sysadmin/app/backend/media && chmod 777 /opt/sysadmin/app/backend/media
  ```
  (Docker lo crearía como root y el contenedor corre como uid 1000 →
  `Permission denied` al subir.)
- Verificar que el bind mount está montado de verdad (el archivo debe aparecer
  en los dos listados):
  ```bash
  docker exec sysadmin_django sh -c 'touch /app/media/PRUEBA && ls -la /app/media'
  ls -la /opt/sysadmin/app/backend/media && rm -f /opt/sysadmin/app/backend/media/PRUEBA
  ```
- Si aparece `Permission denied` al subir: `chown -R 1000:1000 /opt/sysadmin/app/backend/media`.

## Diagnóstico rápido

> Ojo: el paquete `backend/sysadmin/settings/__init__.py` está **vacío**. Para
> `python -c` o scripts usar `DJANGO_SETTINGS_MODULE=sysadmin.settings.base`
> (como hace `manage.py`). Con `sysadmin.settings` Django responde
> *"The SECRET_KEY setting must not be empty"*.
> Para todo lo demás usar `manage.py shell -c '...'`.

```bash
# estado contenedores
sudo docker compose -f /opt/sysadmin/app/docker-compose.yml ps
# salud
sudo docker inspect --format '{{.Name}} {{.State.Health.Status}}' sysadmin_db sysadmin_django sysadmin_nginx
# logs
sudo docker logs --tail 50 sysadmin_django
# HTTPS real (con X-Forwarded-Proto para evitar redirect loop)
curl -sk -H 'X-Forwarded-Proto: https' -o /dev/null -w '%{http_code}\n' https://192.168.1.250:6060/accounts/login/
# documentos registrados vs archivos presentes en disco
sudo docker exec sysadmin_db psql -U sysadmin_user -d sysadmin_db -c "SELECT id, titulo, archivo FROM documentos_documento ORDER BY id;"
ls -laR /opt/sysadmin/app/backend/media/documentos/
```

## Datos migrados (2026-09-24)

Volcado `pg_dump -Fc` desde el Postgres de desarrollo → `scp` → `pg_restore
--clean --if-exists --no-owner --no-privileges` en producción. Conteos
verificados: **67 `usuarios_usuario`** · **23 `activos`** · **2
`documentos_documento`** · **1 `passwords_credencial`** · **1 `soporte_ticket`**.
`manage.py migrate` → "No migrations to apply".

Los 2 PDFs de documentos **no venían en el dump** (un `pg_dump` solo lleva la
BD, no los archivos), pero **ya están en el server** en
`backend/media/documentos/2026/09/` y nginx los sirve con 200:

```
MANUAL_PARA_RESTAURAR_BASE_DE_DATOS.pdf   453458 bytes  PDF 1.7, 7 páginas
Actualizacion_version_de_DMS.pdf          425403 bytes  PDF 1.7, 4 páginas
```

El bind mount es lo que los hace visibles para Django y para nginx a la vez;
con el volumen con nombre anterior, `/media/documentos/...` en el host no
exISTía y "ver" daba 500 aunque el registro estuviera en la BD.

Chequeo rápido de que el repositorio documental sirve:

```bash
ls -la /opt/sysadmin/app/backend/media/documentos/2026/09/
file /opt/sysadmin/app/backend/media/documentos/2026/09/*.pdf
curl -sk -o /dev/null -w '%{http_code} %{size_download}\n' 'https://192.168.1.250:6060/media/documentos/2026/09/MANUAL_PARA_RESTAURAR_BASE_DE_DATOS.pdf'
```

Nota de permisos: el contenedor corre como **root** (`docker exec sysadmin_django id`
→ `uid=0`), por eso escribe aunque `documentos/` sea `root:root 755`. Si algún día
se activa `USER` no-root en el `Dockerfile`, hay que `sudo chown -R 1000:1000
/opt/sysadmin/app/backend/media` (sin `sudo` da *Operation not permitted*).

## Notas de seguridad / fixes aplicados (importante)

- `PASSWORDS_ENCRYPTION_KEY` del `.env` de producción era un valor que **no era
  una clave Fernet válida**, así que `build_fernet()` (`passwords/crypto.py:15`)
  lanzaba `ValueError` y **nada se podía cifrar**: ni la contraseña de OCS en
  Yule (el `save()` del formulario moría con el error) ni el vault de
  credenciales. Corregido el 2026-09-25 con una clave Fernet de 44 caracteres.
  Consecuencia: la 1 credencial que venía del dump local quedó ilegible (estaba
  cifrada con la clave del entorno de desarrollo) y hay que volver a capturarla.
  Verificar que la clave es válida:
  ```bash
  docker exec sysadmin_django python -c 'import os,django;os.environ["DJANGO_SETTINGS_MODULE"]="sysadmin.settings.base";django.setup();from django.conf import settings;from passwords.crypto import build_fernet;build_fernet();print("FERNET_OK len:",len(settings.PASSWORDS_ENCRYPTION_KEY or ""))'
  ```
  Si `PASSWORDS_ENCRYPTION_KEY` estuviera vacía, `build_fernet()` deriva la clave
  de `SECRET_KEY` (`crypto.py:13`) y con gunicorn multi-worker cada worker
  tendría una distinta → el vault se descifra de forma intermitente.
- `SECRET_KEY` **sí** está fijado en el `.env` de producción (67 chars). Si
  faltara, `base.py:15` genera una clave aleatoria en cada arranque: se pierden
  las sesiones en cada restart.
- `base.py` define `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` — sin esto, con `SECURE_SSL_REDIRECT=True` detrás de nginx → **redirect loop** → healthcheck Django falla → compose aborta.
- El healthcheck de `sysadmin_django` manda `X-Forwarded-Proto: https` en la request (requerido, ver `docker-compose.yml`).
- Login: django-axes (5 intentos fallidos → lockout 1h) · auditoría vía signals · mensajes de error genéricos.
- OCS y SysAdmin comparten host: OCS quedó en `:8081` justamente para no tocar los puertos de Hikvision.

## Estado de OCS / Yule

- OCS responde en `http://192.168.1.250:8081/ocsreports/` (HTTP 200) y su API
  REST responde 200 con el usuario OCS `sistemas`.
- La consola **exige un parche** en `html_header.php` (bug PHP 8 de OCS
  2.12.1) o muestra solo el logo. Ver `OCS_INVENTORY_SETUP.md`.
- Yule: configurado en `https://192.168.1.250:6060/yule/configuracion/` con
  URL `http://192.168.1.250:8081/ocsapi/v1`, usuario `sistemas` y su contraseña
  (cifrada con Fernet en `yule_configuracionyule.password_cifrada`). El `.env`
  tiene los mismos valores como fallback. `test_connection()` = `True`.
- **En "Parcial" en el historial = la sincronización ni se ejecutó**, no que
  fuera parcial. Casi siempre es URL sin `/v1` o contraseña vacía
  (`is_configured()` en `client.py:41`). Diagnóstico y causas en
  `OCS_INVENTORY_SETUP.md`.
- Sin equipos inventariados todavía: `SELECT COUNT(*) FROM hardware` = 0 y la API
  devuelve `null`. No es error; falta que un agente OCS reporte.
  (En esta versión de OCS **no** existe la tabla `ocs_computers`; el inventario
  vive en `hardware`, `bios`, `networks`, `software`, etc.)
- OCS y SysAdmin comparten host: OCS quedó en `:8081` justamente para no tocar los puertos de Hikvision.

## Pendientes

1. **Backup a NAS** — `/opt/sysadmin/backups/backup.sh` existe sin destino/cron configurado. Ya corregida la ruta de media (`/opt/sysadmin/app/backend/media/`) y agregado el `.env` al paquete; falta IP/usuario/ruta del NAS. Ojo: el cron actual del server pertenece al Hikvision, no pisarlo.
2. **Agente OCS en clientes** — el `.exe` ya está publicado en `http://192.168.1.250:8081/download/OcsInventoryAgent.exe`; falta instalarlo en al menos un equipo de prueba y confirmar que reporta.
3. **Prueba de Yule** — "Probar conexión" + "Sincronizar ahora" en `/yule/configuracion/` con la URL `http://192.168.1.250:8081/ocsapi/v1`.
4. **Commitear** los cambios de docs, `docker-compose.yml` y `setup_server.sh` (working tree, sin commitear — regla de AGENTS.md).
