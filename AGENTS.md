# SysAdmin · Instrucciones para el agente

## Preferencias del usuario

- **NO hacer `git commit` (ni push, ni otras mutaciones de git) a menos que el usuario lo pida explícitamente.**
  Los cambios se dejan en el working tree y el usuario decide cuándo commitear.
- **Ser conciso: NO explicar, solo dar qué hacer.** Bloques de comandos listos para copiar/pegar + resultado esperado en una línea. Cero teoría, cero contexto, cero preámbulo. Si algo no está claro, preguntar en una línea.

## Estado actual (2026-09-29, producción + OCS + inventario de software)

- **Servidor**: `sistemas@192.168.1.250` (Ubuntu Server 22.04), proyecto en `/opt/sysadmin/app` (Docker Compose).
- **URLs**: HTTPS `https://192.168.1.250:6060` (nginx 443 SSL, cert autofirmado CN=192.168.1.250 · 825 días) · HTTP `:6061` → 301 → HTTPS.
- **Puertos 80/443 del host los ocupa Hikvision** (no se tocan). Por eso OCS quedó en `:8081` y su proxy nginx quedó detenido.
- **Contenedores**: `sysadmin_db` (postgres:15-alpine) · `sysadmin_django` (gunicorn·axles·axes) · `sysadmin_nginx`. Todos arriba, `sysadmin_db` y `sysadmin_django` **healthy**.
- **Login**: `accounts.CustomUser` (superusuarios `Administrador` + el creado en deploy). `usuarios.usuario` = registro de personal/activos, **no** es el modelo de login.
- **Data**: 24 activos inventario · 1 equipo OCS vinculado · 121 filas de software · 67 usuarios_usuario. Los 23 restantes se vinculan manualmente desde Yule › equipos sin match.
- **Fix de deploy aplicado (clave)**: `base.py` → `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` + healthcheck Django manda `X-Forwarded-Proto: https`. Sin esto: redirect loop 301 → contenedor unhealthy → compose aborta.
- **MEDIA_ROOT es bind mount** (`./backend/media:/app/media`) en django **y** nginx, no volumen con nombre. Con volumen, los uploads quedaban dentro de `/var/lib/docker` y no se podían respaldar ni servir. Ver `AGENT_RUNBOOK.md`.
- **Documentos**: los 2 PDFs **sí están en el server** (`backend/media/documentos/2026/09/`) y nginx los sirve con 200. Se habían perdido solo en la máquina local; no hace falta volver a subirlos.
- **OCS**: `http://192.168.1.250:8081/ocsreports/` operativo (usuario `Administrador`, clave en el `.env` del server, tabla de usuarios = `operators`, NO `users`). API JSON en `/ocsapi/v1` verificada 200. Detalle en `OCS_INVENTORY_SETUP.md`.
- **OCS receptor de inventarios**: el handler Perl que ingiere el XML de los agentes vive en **`/ocsinventory`** (raíz), NO en `/ocsreports`. La imagen 2.12.1 nace con el stack roto (`XML::Entities` no existe como paquete en jammy → se instala con `cpanm`; `SOAP::Transport::HTTP2` no lo trae nadie → se crea como alias de `SOAP::Transport::HTTP::Apache`). `bash patch_ocs_server.sh` los reaplica (idempotente) porque un `--force-recreate` los borra. El `DEVICEID` del XML debe cumplir `NOMBRE-AAAA-MM-DD-HH-MM-SS`.
- **OCS `/computers` devuelve un dict indexado por ID** (`{"1": {...}}`), no una lista. `OCSClient._computers_from_payload()` lo normaliza; sin eso el sync contaba 0 equipos.
- **Formato real de la API OCS 2.12** (importante al tocar el parser): `/computers` devuelve un dict indexado por ID y las secciones llegan con la forma de su tabla — `bios` es **lista** (`SSN` = serial del sistema), `hardware.PROCESSORS` es la frecuencia en MHz mientras el nombre está en `PROCESSORT`, `hardware.IPADDR` trae la IP real y `hardware.USERID`/`WORKGROUP` el usuario. `hardware.LASTCOME` es **UTC** (lo evalúa la BD). El software de `/computer/{id}` viene bajo la **clave vacía `""`**, no bajo `"software"`.
- **Tests**: 406, todos verdes. Local `manage.py test`; en el server con `docker exec -e SECURE_SSL_REDIRECT=False -e DEBUG=True sysadmin_django python manage.py test --noinput` (sin esos overrides fallan ~225 por el redirect HTTPS a 6060).
- **Paginación**: listados de activos y tickets paginados a 20 filas (`core/partials/paginacion.html`, templatetag `query_string`).
- **Limpieza de historial**: comando `python manage.py limpiar_historial --dias 365 --media-dias 30 --dry-run` borra auditoría, logs de vault, sync Yule, LogEntry admin, notificaciones leídas y emails enviados antiguos, más archivos huérfanos de media. Cron semanal en `deploy/instalar_cron_limpieza.sh`.
- **CI/CD**: `.github/workflows/ci.yml` ejecuta tests en Python 3.11 con SQLite en cada push/PR.
- **Yule**: configurar en `/yule/configuracion/` con URL `http://192.168.1.250:8081/ocsapi/v1` (termina en `/v1`). La fila en BD tiene prioridad sobre el `.env` (`backend/yule/client.py:241`).
- **Causa raíz del "Yule: Error conexión" + agentes sin registrar (RESUELTO 2026-09-30)**: dos fallas encimadas, ambas de la rotación de contraseña del 29-Sep. (1) MySQL 8 crea `ocsuser` con `caching_sha2_password`, que sobre TCP sin SSL el `DBD::mysql` de Perl no soporta → `DBI connect ... Authentication requires secure connection` → 500. El panel PHP no lo nota porque `mysqli` sí hace el intercambio RSA, así que ** `/ocsreports/` verse bien NO significa que la BD esté bien**. (2) Los `.conf` de Apache se generan con `sed` desde `$OCS_DB_PASS` pero **solo `if [ ! -f ... ]`**, y viven en el volumen `httpdconfdata` → se crearon una vez con `ocspass` y la rotación nunca llegó. Afecta a `zz-ocsinventory-restapi.conf` (API) **y a `z-ocsinventory-server.conf` (receptor `/ocsinventory`, los agentes)**, ese segundo es el que no se ve venir. Arreglo: `ALTER USER 'ocsuser'@'%' IDENTIFIED WITH mysql_native_password BY ...` + `sed` del password en ambos `.conf` + `apachectl -k graceful` (no hace falta recrear el contenedor, así no se pierden los parches de Perl). **El mensaje de Yule "verificar credenciales" es falso: el 500 sale igual sin autenticarse.** Blindaje: `deploy/ocs-db-init/01-ocsuser-native-auth.sh` en `sql/` (persiste ante reconstrucción de la BD; MySQL solo corre `initdb.d` con el datadir vacío) + `deploy/ocs_verificar_api.sh [--arreglar]` (repara *drift* sin borrar el volumen). Detalle en `OCS_INVENTORY_SETUP.md` → *"La API y el receptor mueren si la BD no autentica en TCP plano"*.
- **Pendiente**: `MYSQL_ROOT_PASSWORD : rootpass` en el compose de OCS sigue sin rotar. No causó el fallo anterior, pero es root débil en un archivo ya tocado.
- **Causa raíz del "OCS no registra equipos" (RESUELTO 2026-09-28)**: el agente apuntaba a `/ocsreports` o `/ocsapi/v1`. El receptor es **`/ocsinventory`** (raíz, sin subruta). Con la URL corregida el agente real reporta `200` y Yule ya muestra el inventario completo. Los campos vacíos (serial, procesador, IP, MAC, usuario) eran bugs del parser de Yule, no de OCS. Detalle en la sección 0 de `INFORME_OCS_YULE_2026-09-25.md`.

## Inventario de software (2026-09-29)

- **Modelo** `inventario.SoftwareInstalado`: una fila por (activo, nombre, versión) con `fecha_instalacion` / `fecha_ultima_vista` / `fecha_retiro` / `presente`. Lo que se da de baja **no se borra**, para conservar cuándo se detectó el cambio. Migración `0009_softwareinstalado`.
- **Páginas**: `/inventario/<pk>/software/` (el activo) y `/inventario/software/` (qué programas hay y en cuántos de los 24 activos está cada uno). La segunda es la razón de guardar en base: antes no había forma de preguntar "quién tiene Office".
- **La vista lee de la BD, no de OCS**. El botón "Leer de OCS" fuerza la lectura. Abrir la página no toca OCS.
- **`aplicar_reporte()`** (`inventario/software_sync.py`) compara por conjuntos y **solo escribe diferencias**: un reporte idéntico da 0 escrituras.
- **Regla que gobierna el sync**: los faltantes (bajas) solo se calculan si el reporte llegó de verdad. Si OCS no responde o el equipo no está vinculado, no se toca una fila. Sin esto un equipo apagado el fin de semana aparecería vacío y el lunes "reinstalaría" sus 122 programas. Un reporte que llega vacío **sí** marca todo como retirado, porque es información real.
- **`"Unavailable"`** es la cadena literal que OCS devuelve cuando el agente no informa el campo. Se guarda como vacío: si se guardara, cada vuelta crearía una versión nueva y daría de baja la anterior.
- **Coexistencia de versiones** del mismo nombre (runtimes de 32 y 64 bits) se distingue de un reemplazo mirando si la versión anterior **sigue en el reporte**, no en la base: el retiro se calcula después del alta, así que en la base las dos cosas se ven iguales.
- **Sincronización**: `python manage.py sincronizar_software` (`--dry-run`, `--verbose`, `--activo PK`, `--pausa SEG`). Los errores van aislados por equipo, un corte de OCS no deja la base a medias.
- **Cron software**: `/etc/cron.d/sysadmin-sincronizar-software`, una vez al día a las **03:07**. Instalar con `sudo bash /opt/sysadmin/app/deploy/instalar_cron_software.sh` (hace falta sudo: `docker exec` corre como root). Log en `/var/log/sysadmin-software-sync.log`. Se cambió de 2 veces por hora a diario porque con 24 activos no se detectan instalaciones en minutos.
- **Cron limpieza**: `/etc/cron.d/sysadmin-limpiar-historial`, domingos a las **04:00**. Instalar con `sudo bash /opt/sysadmin/app/deploy/instalar_cron_limpieza.sh`. Log en `/var/log/sysadmin-limpiar-historial.log`.
- **Hook en el sync de equipos**: `_sincronizar_software_tras_equipos()` lee el software **solo** de los activos que aún no tienen nada guardado, y va después de guardar el log para que un fallo ahí no tumbe el sync de hardware. Relee la flota entera sería N requests extra en cada vuelta.
- **Pendiente**: solo **1 de 24 activos** tiene equipo OCS vinculado (W11F35F), y es el único con software guardado. El resto se vincula desde Yule › equipos sin match.

- **Manual del agente**: `MANUAL_AGENTE_OCS.md` es el procedimiento oficial para instalar y configurar el agente OCS en los equipos cliente (instalación gráfica y silenciosa, verificación, `ocsinventory.ini`, tabla de errores y desinstalación). Es el documento que se entrega a Sistemas para el despliegue masivo.
- **Pendientes operativos**: backup a NAS (falta IP/usuario/ruta) · `sudo systemctl reload cron` tras editar cualquier cron.

---

## Contexto de producción (deploy 2026-09-24)

- Servidor: `sistemas@192.168.1.250` (Ubuntu Server). Proyecto en `/opt/sysadmin/app` (docker compose).
- Acceso web: `https://192.168.1.250:6060` (HTTPS) · `http://192.168.1.250:6061` (301→https). Cert autofirmado.
- Contenedores: `sysadmin_db` (postgres:15-alpine), `sysadmin_django`, `sysadmin_nginx`.
- `.env` en `/opt/sysadmin/app/.env` (producción: `DEBUG=False`). El repositorio local (working tree) es la fuente; el servidor es una copia con `scp` archivo por archivo.
- **Settings separados**: `sysadmin.settings.base` (común), `sysadmin.settings.local` (desarrollo SQLite/HTTP), `sysadmin.settings.production` (PostgreSQL/HTTPS). `manage.py` usa `local`; `wsgi.py` usa `production`; `docker-compose.yml` fuerza `DJANGO_SETTINGS_MODULE=sysadmin.settings.production`.
- `manage.py` y `wsgi.py` cargan `.env` automáticamente con `python-dotenv` (no sobreescriben variables ya existentes; en Docker no tiene efecto).
- `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` está en `base.py` (requerido por `SECURE_SSL_REDIRECT=True` detrás de nginx).
- nginx ahora oculta la versión (`server_tokens off`) y envía HSTS en HTTPS.
- **Deploy siempre con `docker compose up -d --force-recreate django`**: subir archivos sin recrear deja gunicorn con el código viejo y produce 500. Verificar con `md5sum` de cada archivo antes de reiniciar.
- Pendientes: backup a NAS (script `/opt/sysadmin/backups/backup.sh` sin destino/cron).
