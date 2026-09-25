# SysAdmin · Instrucciones para el agente

## Preferencias del usuario

- **NO hacer `git commit` (ni push, ni otras mutaciones de git) a menos que el usuario lo pida explícitamente.**
  Los cambios se dejan en el working tree y el usuario decide cuándo commitear.
- **Ser conciso: NO explicar, solo dar qué hacer.** Bloques de comandos listos para copiar/pegar + resultado esperado en una línea. Cero teoría, cero contexto, cero preámbulo. Si algo no está claro, preguntar en una línea.

## Estado actual (2026-09-25, deploy producción + OCS)

- **Servidor**: `sistemas@192.168.1.250` (Ubuntu Server 22.04), proyecto en `/opt/sysadmin/app` (Docker Compose).
- **URLs**: HTTPS `https://192.168.1.250:6060` (nginx 443 SSL, cert autofirmado CN=192.168.1.250 · 825 días) · HTTP `:6061` → 301 → HTTPS.
- **Puertos 80/443 del host los ocupa Hikvision** (no se tocan). Por eso OCS quedó en `:8081` y su proxy nginx quedó detenido.
- **Contenedores**: `sysadmin_db` (postgres:15-alpine) · `sysadmin_django` (gunicorn·axles·axes) · `sysadmin_nginx`. Todos arriba, `sysadmin_db` y `sysadmin_django` **healthy**.
- **Login**: `accounts.CustomUser` (superusuarios `Administrador` + el creado en deploy). `usuarios.usuario` = registro de personal/activos, **no** es el modelo de login.
- **Data migrada**: 67 usuarios_usuario · 23 activos inventario · 2 documentos · 1 credencial passwords · 1 ticket (restore `pg_restore --clean` desde dump local, verificado con `\dt` + conteos).
- **Fix de deploy aplicado (clave)**: `base.py` → `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` + healthcheck Django manda `X-Forwarded-Proto: https`. Sin esto: redirect loop 301 → contenedor unhealthy → compose aborta.
- **MEDIA_ROOT es bind mount** (`./backend/media:/app/media`) en django **y** nginx, no volumen con nombre. Con volumen, los uploads quedaban dentro de `/var/lib/docker` y no se podían respaldar ni servir. Ver `AGENT_RUNBOOK.md`.
- **Documentos**: los 2 PDFs **sí están en el server** (`backend/media/documentos/2026/09/`) y nginx los sirve con 200. Se habían perdido solo en la máquina local; no hace falta volver a subirlos.
- **OCS**: `http://192.168.1.250:8081/ocsreports/` operativo (usuario `Administrador`, clave en el `.env` del server, tabla de usuarios = `operators`, NO `users`). Requiere un parche en `html_header.php` (bug PHP 8) o la consola muestra solo el logo. API JSON en `/ocsapi/v1` verificada 200. Detalle en `OCS_INVENTORY_SETUP.md`.
- **Yule**: configurar en `/yule/configuracion/` con URL `http://192.168.1.250:8081/ocsapi/v1` (termina en `/v1`). La fila en BD tiene prioridad sobre el `.env` (`backend/yule/client.py:241`).
- **Pendientes operativos**: backup a NAS (falta IP/usuario/ruta) · instalar el agente OCS en un cliente de prueba (ya publicado en `http://192.168.1.250:8081/download/OcsInventoryAgent.exe`) · commitear los cambios del working tree.

---


## Contexto de producción (deploy 2026-09-24)

- Servidor: `sistemas@192.168.1.250` (Ubuntu Server). Proyecto en `/opt/sysadmin/app` (docker compose).
- Acceso web: `https://192.168.1.250:6060` (HTTPS) · `http://192.168.1.250:6061` (301→https). Cert autofirmado.
- Contenedores: `sysadmin_db` (postgres:15-alpine), `sysadmin_django`, `sysadmin_nginx`.
- `.env` en `/opt/sysadmin/app/.env` (producción: `DEBUG=False`). El repositorio local (working tree) es la fuente; el servidor es solo un copia vía `rsync` con excludes (`venv/`, `backend/media/`, `tmp_scratch*`).
- `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` está en `base.py` (requerido por `SECURE_SSL_REDIRECT=True` detrás de nginx).
- Pendientes: backup a NAS (script `/opt/sysadmin/backups/backup.sh` sin destino/cron) e integración OCS/Yule (endpoint no configurado en el servidor).
