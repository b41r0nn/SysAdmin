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
- **OCS**: `http://192.168.1.250:8081/ocsreports/` operativo (usuario `Administrador`, clave en el `.env` del server, tabla de usuarios = `operators`, NO `users`). API JSON en `/ocsapi/v1` verificada 200. Detalle en `OCS_INVENTORY_SETUP.md`.
- **OCS receptor de inventarios**: el handler Perl que ingiere el XML de los agentes vive en **`/ocsinventory`** (raíz), NO en `/ocsreports`. La imagen 2.12.1 nace con el stack roto (`XML::Entities` no existe como paquete en jammy → se instala con `cpanm`; `SOAP::Transport::HTTP2` no lo trae nadie → se crea como alias de `SOAP::Transport::HTTP::Apache`). `bash patch_ocs_server.sh` los reaplica (idempotente) porque un `--force-recreate` los borra. El `DEVICEID` del XML debe cumplir `NOMBRE-AAAA-MM-DD-HH-MM-SS`.
- **OCS `/computers` devuelve un dict indexado por ID** (`{"1": {...}}`), no una lista. `OCSClient._computers_from_payload()` lo normaliza; sin eso el sync contaba 0 equipos.
- **Tests en el server**: correr con `docker exec -e SECURE_SSL_REDIRECT=False -e DEBUG=True sysadmin_django python manage.py test --noinput`. Sin esos overrides fallan ~225 tests por el redirect HTTPS a 6060 y por el `EOFError` de borrar la BD de pruebas.
- **Yule**: configurar en `/yule/configuracion/` con URL `http://192.168.1.250:8081/ocsapi/v1` (termina en `/v1`). La fila en BD tiene prioridad sobre el `.env` (`backend/yule/client.py:241`).
- **Causa raíz del "OCS no registra equipos" (RESUELTO 2026-09-28)**: el agente apuntaba a `/ocsreports` o `/ocsapi/v1`. El receptor es **`/ocsinventory`** (raíz, sin subruta). Con la URL corregida el agente real reporta `200` y Yule ya muestra el inventario completo. Los campos vacíos (serial, procesador, IP, MAC, usuario) eran bugs del parser de Yule, no de OCS. Detalle en la sección 0 de `INFORME_OCS_YULE_2026-09-25.md`.
- **Formato real de la API OCS 2.12** (importante al tocar el parser): `/computers` devuelve un dict indexado por ID y las secciones llegan con la forma de su tabla — `bios` es **lista** (`SSN` = serial del sistema), `hardware.PROCESSORS` es la frecuencia en MHz mientras el nombre está en `PROCESSORT`, `hardware.IPADDR` trae la IP real y `hardware.USERID`/`WORKGROUP` el usuario. `hardware.LASTCOME` es **UTC** (lo evalúa la BD). El software de `/computer/{id}` viene bajo la **clave vacía `""`**, no bajo `"software"`.
- **Manual del agente**: `MANUAL_AGENTE_OCS.md` es el procedimiento oficial para instalar y configurar el agente OCS en los equipos cliente (instalación gráfica y silenciosa, verificación, `ocsinventory.ini`, tabla de errores y desinstalación). Es el documento que se entrega a Sistemas para el despliegue masivo.
- **Pendientes operativos**: `OCS_OPT_LOGLEVEL` volver a `0` (está en `512`) · rotar la contraseña de la BD de OCS (sigue la de fábrica) · backup a NAS (falta IP/usuario/ruta) · commitear los cambios del working tree.

---


## Contexto de producción (deploy 2026-09-24)

- Servidor: `sistemas@192.168.1.250` (Ubuntu Server). Proyecto en `/opt/sysadmin/app` (docker compose).
- Acceso web: `https://192.168.1.250:6060` (HTTPS) · `http://192.168.1.250:6061` (301→https). Cert autofirmado.
- Contenedores: `sysadmin_db` (postgres:15-alpine), `sysadmin_django`, `sysadmin_nginx`.
- `.env` en `/opt/sysadmin/app/.env` (producción: `DEBUG=False`). El repositorio local (working tree) es la fuente; el servidor es solo un copia vía `rsync` con excludes (`venv/`, `backend/media/`, `tmp_scratch*`).
- `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` está en `base.py` (requerido por `SECURE_SSL_REDIRECT=True` detrás de nginx).
- Pendientes: backup a NAS (script `/opt/sysadmin/backups/backup.sh` sin destino/cron) e integración OCS/Yule (endpoint no configurado en el servidor).
