# SysAdmin · Instrucciones para el agente

## Preferencias del usuario

- **NO hacer `git commit` (ni push, ni otras mutaciones de git) a menos que el usuario lo pida explícitamente.**
  Los cambios se dejan en el working tree y el usuario decide cuándo commitear.

## Estado actual (2026-09-24, deploy producción)

- **Servidor**: `sistemas@192.168.1.250` (Ubuntu Server 22.04), proyecto en `/opt/sysadmin/app` (Docker Compose).
- **URLs**: HTTPS `https://192.168.1.250:6060` (nginx 443 SSL, cert autofirmado CN=192.168.1.250 · 825 días) · HTTP `:6061` → 301 → HTTPS.
- **Contenedores**: `sysadmin_db` (postgres:15-alpine) · `sysadmin_django` (gunicorn·axles·axes) · `sysadmin_nginx`. Todos arriba, `sysadmin_db` y `sysadmin_django` **healthy**.
- **Login**: `accounts.CustomUser` (superusuarios `Administrador` + el creado en deploy). `usuarios.usuario` = registro de personal/activos, **no** es el modelo de login.
- **Data migrada**: 67 usuarios_usuario · 23 activos inventario · 2 documentos · 1 credencial passwords · 1 ticket (restore `pg_restore --clean` desde dump local, verificado con `\dt` + conteos).
- **Fix de deploy aplicado (clave)**: `base.py` → `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` + healthcheck Django manda `X-Forwarded-Proto: https`. Sin esto: redirect loop 301 → contenedor unhealthy → compose aborta.
- **Pendientes operativos**: backup a NAS (script `/opt/sysadmin/backups/backup.sh` sin destino/cron) · OCS/Yule "no está configurado" (falta endpoint/credenciales) · commit de los fixes (working tree, sin versionar aún — ver SYSADMIN_HANDOFF.md).

---


## Contexto de producción (deploy 2026-09-24)

- Servidor: `sistemas@192.168.1.250` (Ubuntu Server). Proyecto en `/opt/sysadmin/app` (docker compose).
- Acceso web: `https://192.168.1.250:6060` (HTTPS) · `http://192.168.1.250:6061` (301→https). Cert autofirmado.
- Contenedores: `sysadmin_db` (postgres:15-alpine), `sysadmin_django`, `sysadmin_nginx`.
- `.env` en `/opt/sysadmin/app/.env` (producción: `DEBUG=False`). El repositorio local (working tree) es la fuente; el servidor es solo un copia vía `rsync` con excludes (`venv/`, `backend/media/`, `tmp_scratch*`).
- `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` está en `base.py` (requerido por `SECURE_SSL_REDIRECT=True` detrás de nginx).
- Pendientes: backup a NAS (script `/opt/sysadmin/backups/backup.sh` sin destino/cron) e integración OCS/Yule (endpoint no configurado en el servidor).
