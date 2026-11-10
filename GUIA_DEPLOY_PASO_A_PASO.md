# Guía de Deploy Paso a Paso — SysAdmin

Despliegue en producción sobre el servidor **192.168.1.250** (Ubuntu 22.04.5 LTS).
Fecha de referencia: 2026-09-29 · Tag: `v2.4.0-2026-09-29`

> **Deploy ya hecho.** El servidor está en producción con `v2.4.0-2026-09-29`.
> Esta guía sirve para el **siguiente** deploy o para rehacer el servidor. La
> lista corta de lo que hay que correr está en `CHECKLIST_DEPLOY.md`.

> Requiere: acceso SSH `sistemas@192.168.1.250` con sudo.

---

## 0. Estado del servidor (verificado)

| Ítem                     | Estado                                                                |
| ------------------------ | --------------------------------------------------------------------- |
| Docker / Compose         | ✅ 29.7.2 / v5.4.0 (ya instalado — el setup lo omite)                  |
| UFW                      | ✅ Activo: `22, 3000, 8000` (+ Se agregarán `6060/6061`)               |
| Hikvision Extractor      | ✅ Corriendo (`8000`, `80`) — no se toca                               |
| `/opt/sysadmin`          | ❌ No existe → setup limpio                                            |
| Dirs libres de conflicto | `6060`, `6061` sin uso; red `sysadmin_net`; contenedores `sysadmin_*` |

---

## 1. Copiar el proyecto al servidor

```bash
# Opción A — git clone (recomendada; trae solo lo versionado, sin .env ni certs)
sudo git clone https://github.com/b41r0nn/SysAdmin.git /opt/sysadmin/app
cd /opt/sysadmin/app
sudo git checkout v2.4.0-2026-09-29

# Opción B — rsync desde Windows (WSL2): copia el working tree local tal cual
cd /mnt/c/Users/Sistemas/OneDrive\ -\ REPRESENTACIONES.../Vscode/SysAdmin
rsync -av --exclude .git --exclude .env --exclude 'nginx/certs' --exclude '__pycache__' \
  ./ sistemas@192.168.1.250:/opt/sysadmin/app/
```

Verificar que quedó la estructura esperada:

```bash
cd /opt/sysadmin/app && ls
# → CHECKLIST_DEPLOY.md  docker-compose.yml  nginx/  backend/  setup_server.sh ...
```

> Instalar/actualizar utilidades del SO **no es necesario** (Docker+compose+ufw ya existen).
> Si se quisiera igualmente: `sudo bash setup_server.sh` es seguro — saltea Docker y solo
> agrega reglas UFW y el certificado (Paso 2), sin destruir nada del host.

---

## 2. Generar el certificado HTTPS autofirmado

```bash
sudo mkdir -p /opt/sysadmin/app/nginx/certs
# si no existe server.crt:
sudo openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
  -keyout /opt/sysadmin/app/nginx/certs/server.key \
  -out /opt/sysadmin/app/nginx/certs/server.crt \
  -subj "/CN=192.168.1.250"
sudo chmod 600 /opt/sysadmin/app/nginx/certs/server.key
```

> Reutiliza el paso 7 de `setup_server.sh` si ya lo ejecutaste.

---

## 3. Creamos el `.env` de producción

Claves **obligatorias** que el contenedor lee vía `env_file` (`docker-compose.yml`):

```bash
cd /opt/sysadmin/app

# Generar las dos claves cripto (guardar copia en tu gestor de passwords!)
echo "SECRET_KEY:           $(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
echo "PASSWORDS_ENCRYPTION: $(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# password de postgres:
echo "POSTGRES_PASSWORD:    $(openssl rand -hex 24)"
```

Crear archivo `/opt/sysadmin/app/.env` con:

```ini
# ── Obligatorios ───────────────────────────────
SECRET_KEY=<generada arriba>
PASSWORDS_ENCRYPTION_KEY=<generada arriba>
DEBUG=False
ALLOWED_HOSTS=192.168.1.250,localhost,127.0.0.1

# ── Base de datos ──────────────────────────────
POSTGRES_DB=sysadmin
POSTGRES_USER=sysadmin_user
POSTGRES_PASSWORD=<generada arriba>
DB_HOST=db
DB_PORT=5432

# ── Seguridad HTTP (HTTPS detrás de nginx) ─────
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
TRUSTED_ORIGINS=https://192.168.1.250:6060,https://localhost:6060

# ── OCS (Yule) ─────────────────────────────────
OCS_BASE_URL=http://192.168.1.250:8081/ocsapi/v1
OCS_USER=<usuario_ocs>
OCS_TOKEN=<token_ocs>
OCS_VERIFY_SSL=True
```

> **⚠️ Claves cripto:** falta `SECRET_KEY` → producción **no arranca**; falta
> `PASSWORDS_ENCRYPTION_KEY` → se deriva de `SECRET_KEY` (aviso `W001`, no bloquea);
> rotar `SECRET_KEY` sin clave propia deja **ilegible** el vault; poner una clave
> nueva con datos ya cifrados requiere **re-cifrar** antes.

```bash
sudo chmod 600 /opt/sysadmin/app/.env
```

> Nota OCS: `build_client()` prioriza la fila `ConfiguracionYule` guardada en BD
> (`/yule/configuracion/`) sobre el `.env`. Con BD nueva no hay config → vale el `.env`.

---

## 4. Agregar reglas de firewall (solo SysAdmin)

```bash
sudo ufw allow 6060/tcp
sudo ufw allow 6061/tcp
sudo ufw status numbered
# confirmar: 22, 3000, 8000 (existentes) + 6060, 6061 (nuevas)
```

---

## 5. Build y levantamiento del stack

```bash
cd /opt/sysadmin/app

# Extra: con --no-cache si hubo historial de cache malo (WSL/mnt-c).
# En servidor nativo alcanza el build normal, pero no daña usar --no-cache.
sudo docker compose build --no-cache django

# Levantar
sudo docker compose up -d

# Estado (esperar hasta que db y django estén Healthy)
sudo docker ps --filter name=sysadmin

# Logs si algo falla
sudo docker compose logs --tail 50 django
```

> El entrypoint ejecuta automáticamente `migrate --noinput` y `collectstatic --noinput`
> antes de arrancar gunicorn. Nginx redirige `6061 → 6060`.

---

## 6. Superusuario inicial (solo primera vez)

```bash
sudo docker exec -it sysadmin_django python manage.py createsuperuser
```

---

## 7. Validación post-deploy

Desde tu PC:

```bash
# HTTPS (aceptar cert autofirmado en el navegador)
#   https://192.168.1.250:6060/accounts/login/
# HTTP puro → debe redireccionar
#   http://192.168.1.250:6061/accounts/login/
#   → 301 Moved Permanently → https://192.168.1.250:6060/accounts/login/
```

Desde el servidor:

```bash
curl -sk -o /dev/null -w "%{http_code}\n" https://localhost:6060/accounts/login/   # 200
curl -sk -I http://localhost:6061/accounts/login/                                  # 301
sudo docker exec sysadmin_django python manage.py check                            # 0 issues
sudo docker logs --tail 20 sysadmin_django                                         # sin tracebacks
```

### Validación funcional

- [ ] Login OK → dashboard.
- [ ] Login erróneo ×5 → lockout (429) y registro `cuenta_bloqueada`.
- [ ] `/admin/` accesible.
- [ ] `/yule/api/test-conexion/` → `{"success": true}` (si OCS alcanzable; si no, 401/error controlado).
- [ ] `docker exec sysadmin_django python -c "import requests; print(requests.get('http://192.168.1.250:8081/ocsapi/v1/computers', timeout=5).status_code)"` → 200/401 (no timeout).
- [ ] Sync manual: `/yule/sincronizar/` o `docker exec sysadmin_django python manage.py sync_ocs`.
- [ ] Inventario de software: `sincronizar_software --dry-run --verbose` lista activos sin escribir, y las páginas `/inventario/<pk>/software/` y `/inventario/software/` cargan 200.

---

## 7b. Cron del inventario de software

El cron no está en el repo como servicio: se instala en el host. Hay que
instalarlo **una vez por servidor**, con sudo (porque `docker exec` corre como
root).

```bash
sudo bash /opt/sysadmin/app/deploy/instalar_cron_software.sh
sudo grep sincronizar /etc/cron.d/sysadmin-sincronizar-software
```

Espera `7 3 * * *` (una vez al día a las 03:07). Log en
`/var/log/sysadmin-software-sync.log`, legible sin sudo.

Para no esperar a la primera vuelta, correr el mismo comando a mano:

```bash
sudo docker exec sysadmin_django python manage.py sincronizar_software --verbose --pausa 2
tail -20 /var/log/sysadmin-software-sync.log
```

Si se edita la frecuencia: cambiar la última línea del `.cron` y
`sudo service cron reload`.

---

## 7c. Cron de limpieza de historial (módulo de Configuración)

> **Pasa por alto con un despliegue normal, y sin este paso la pantalla de retención no tiene efecto.**

Desde el módulo de Configuración, `limpiar_historial` lee la retención de
`/administracion/datos/` cuando se lo llama **sin** `--dias` ni `--media-dias`
(un argumento explícito sigue ganando, para poder forzar a mano). Por eso
`deploy/instalar_cron_limpieza.sh` dejó de pasarlos.

Pero el archivo del cron vive en **`/etc/cron.d/sysadmin-limpiar-historial` del
host**, fuera del contenedor. Copiar el código y reconstruir la imagen (§8b)
**no lo toca**: el cron viejo sigue ejecutando `limpiar_historial --dias 365
--media-dias 30`, la limpieza semanal ignora lo que el administrador ponga en la
pantalla y nadie se entera. Una opción de configuración que el proceso real
ignora es peor que no tenerla.

Después de desplegar el código (el orden no importa: el comando sin argumentos
usa los mismos 365 y 30 de fábrica), en el servidor:

```bash
sudo bash /opt/sysadmin/app/deploy/instalar_cron_limpieza.sh
sudo cat /etc/cron.d/sysadmin-limpiar-historial
sudo journalctl -u cron --since "-2 min" | grep RELOAD
```

> **`systemctl reload cron` no funciona en este servidor**: responde *Job type reload is not applicable for unit cron.service*. El que sirve es `sudo service cron reload`. Y en realidad **no hace falta ninguno**: cron vigila `/etc/cron.d` y relee solo — se comprueba en `sudo journalctl -u cron`, que deja un renglón `(*system*<archivo>) RELOAD`. El reload es por si no quieres esperar ese minuto.

Espera `0 4 * * 0 root cd /opt/sysadmin/app && docker exec sysadmin_django python
manage.py limpiar_historial >> /var/log/sysadmin-limpiar-historial.log 2>&1`:
domingos 04:00 y **sin** `--dias` ni `--media-dias`. Si todavía aparecen,
el script del servidor es el viejo: `tar xzf` de nuevo y repetir.

Comprobar que la configuración llega al comando (sin borrar nada):

```bash
sudo docker exec sysadmin_django python manage.py limpiar_historial --dry-run
```

Cambiar la retención en la pantalla Datos (p. ej. a 90) y repetir: el corte que informa debe moverse con ella.

Lo segundo que hay que saber al leer ese log: **el barrido de `media` solo informa**. Lista los archivos que ningún registro referencia y termina con «no se borraron». Para borrarlos de verdad hay que correrlo a mano con `--borrar-media-huerfana`, y conviene mirar la lista antes: el 2026-11-10 esa lista incluía **7 actas firmadas escaneadas reales** cuya fila ya no existía. Un archivo sin referencia puede seguir siendo un documento legal.

Y lo que hay que saber al leer ese log: **si el comando no puede leer la retención** (base a medio migrar, tabla de configuración ausente) **no borra nada** y escribe `NO SE BORRÓ NADA`. No es que no hubiera qué borrar: es que sin la política borraría más de lo que el administrador eligió conservar, y lo borrado no se recupera. Se arregla la base y se vuelve a correr, o se pasan `--dias` y `--media-dias` explícitos si hace falta purgar ya.

---

## 7d. Caché tras una migración de datos

El módulo de Configuración cachea el catálogo de módulos y la matriz de permisos
**300 segundos** (`SEGUNDOS_CACHE` en `administracion/registro.py`). Las señales
(`post_save`/`post_delete`) la invalidan al guardar por instancia, pero una
**migración de datos escrita con `queryset.update()`** (la `0009`, que cambia el
enlace «Configuración» del menú, lo hace) no dispara señales.

**En un despliegue normal NO hace falta limpiar la caché.** Se verificó en el
código, no se supuso:

- En producción la caché es `FileBasedCache` en `/tmp/sysadmin_django_cache`
  (`settings/production.py`; `DJANGO_CACHE_DIR` no está definida en
  `docker-compose.yml` ni en `.env.example`), o sea **dentro del contenedor**.
- `docker-compose.yml` monta en `django` solo `static_volume:/app/staticfiles` y
  `./backend/media:/app/media`. **No hay volumen en `/tmp`.**
- El despliegue es `docker compose build django nginx` + `up -d django nginx`
  (§8b): el contenedor se **recrea** y arranca con la caché vacía.
- `backend/entrypoint.sh` corre `migrate --noinput` (línea 5) **antes** de
  `exec gunicorn` (línea 8): la migración se aplica antes de que ningún worker
  pueda servir una petición, y el código anterior nunca escribió esas claves.

Así que no hay ventana de enlace viejo. (Varias lecturas se equivocaron
aquí: decían que la caché «vive en disco» y sobrevive al reinicio. Vive en el
disco **del contenedor**, no del host.) Matiz: `up -d` solo recrea si la imagen
cambió; una migración nueva implica código nuevo, así que la imagen cambia.

**Cuándo sí.** Si una migración de datos se lanza **a mano** con `docker exec`
sobre un contenedor **ya corriendo**, no se reinicia nada: la caché sobrevive y un
valor viejo puede servirse hasta 300 s. Un `docker restart` simple tampoco ayuda
(conserva la capa de escritura del contenedor, incluido `/tmp`); solo recrear lo
hace. En ese caso, limpiarla justo después:

```bash
docker exec sysadmin_django python manage.py migrate --noinput
docker exec sysadmin_django python manage.py shell -c "from django.core.cache import cache; cache.clear()"
```

Vale para cualquier migración de datos futura sobre `Modulo`, `Rol`,
`PermisoRol` o `ConfiguracionSistema`. (`ConfiguracionSistema` no se cachea: se lee
en vivo; la caché afecta a módulos y permisos.)

Tras el `migrate` del primer despliegue del módulo, confirmar que las tablas
quedaron sembradas:

```bash
docker exec sysadmin_django python manage.py shell -c "
from administracion.models import Modulo, Rol, PermisoRol
print(Modulo.objects.count(), Rol.objects.count(), PermisoRol.objects.count())"
```

Esperado: `10 4 40`.

---

## 8. Backup → NAS

Configurar `/opt/sysadmin/backups/backup.sh` (creado por setup_server.sh) con IP, ruta y
usuario NAS; ya queda en cron (2:00 AM). Verificar ejecución manual:

```bash
sudo /opt/sysadmin/backups/backup.sh
cat /opt/sysadmin/backups/backup.log
```

---

## 8b. Actualizar una instalación existente

`/opt/sysadmin/app` **no es un clon de git**: el código se copia. Desde el
repo en Windows (Git Bash):

```bash
# LF obligatorio: con autocrlf, git archive mete CRLF y entrypoint.sh no arranca.
git -c core.autocrlf=false -c core.eol=lf archive --format=tar.gz -o /tmp/release.tgz master     backend nginx/nginx.conf nginx/Dockerfile docker-compose.yml deploy .env.example
scp /tmp/release.tgz sistemas@192.168.1.250:/tmp/
```

En el servidor:

```bash
cd /opt/sysadmin/app
TS=$(date +%F-%H%M); mkdir -p backups/$TS
docker exec sysadmin_db sh -c 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc' > backups/$TS/db.dump
tar xzf /tmp/release.tgz && rm /tmp/release.tgz
docker compose build django nginx
docker compose up -d django nginx
docker ps --filter name=sysadmin_   # django debe quedar (healthy)
```

**Antes de dar por cerrado un despliegue, mirar si cambió algo bajo `deploy/`**: lo que se instala en el host (`/etc/cron.d/`) no viaja con la imagen. Hoy son los crons de §7b y §7c; el de limpieza (§7c) hay que reinstalarlo en el módulo de Configuración o la retención configurable no tiene efecto.

Desde 2026-10-19 el contenedor de Django corre como usuario `app` (UID 1000 =
`sistemas`) y el código va **dentro de la imagen**: un cambio de código no se
ve hasta reconstruir. `backend/media/` debe pertenecer a `sistemas` (UID 1000);
si aparece algo de root ahí, `docker run --rm -v /opt/sysadmin/app/backend/media:/m
--entrypoint chown -u 0 app-django -R 1000:1000 /m`.

## 9. Rollback

`/opt/sysadmin/app` no es clon de git: se vuelve atrás desplegando el commit
anterior con el mismo procedimiento de §8b (cambiando `master` por el tag o
commit bueno):

```bash
# En Windows (Git Bash)
git -c core.autocrlf=false -c core.eol=lf archive --format=tar.gz -o /tmp/release.tgz <tag-o-commit-bueno>     backend nginx/nginx.conf nginx/Dockerfile docker-compose.yml deploy .env.example
scp /tmp/release.tgz sistemas@192.168.1.250:/tmp/

# En el servidor
cd /opt/sysadmin/app
tar xzf /tmp/release.tgz && rm /tmp/release.tgz
docker compose build django nginx && docker compose up -d django nginx
```

Si además hay que devolver la base de datos al backup tomado antes del deploy
(se pierde lo escrito después):

```bash
docker compose stop django
docker exec -i sysadmin_db sh -c 'pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists' < backups/<TS>/db.dump
docker compose start django
```

> La BD vive en el volumen `postgres_data`; además del `db.dump` de cada deploy,
> `backup.timer` hace restic diario (lun–sáb 02:30) en `/mnt/hdd1t`.

---

## 10. Pendientes tras el deploy

- [ ] Renovar cert autofirmado (~dic 2028).
- [ ] Definir credenciales OCS reales en BD o `.env`.
- [ ] OCS 8081: solo abrir en UFW si se expone fuera de la LAN; no exponer el HTTP plano sin TLS.
