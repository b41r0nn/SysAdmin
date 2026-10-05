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
echo "PASSWORDS_ENCRYPTION: $(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"

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
OCS_VERIFY_SSL=False
```

> **⚠️ CRÍTICO:** si faltan `SECRET_KEY`/`PASSWORDS_ENCRYPTION_KEY`, el vault de passwords
> se vuelve ilegible (clave random por arranque). Definirlas ANTES del primer `up`.

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
`sudo systemctl reload cron`.

---

## 8. Backup → NAS

Configurar `/opt/sysadmin/backups/backup.sh` (creado por setup_server.sh) con IP, ruta y
usuario NAS; ya queda en cron (2:00 AM). Verificar ejecución manual:

```bash
sudo /opt/sysadmin/backups/backup.sh
cat /opt/sysadmin/backups/backup.log
```

---

## 9. Rollback

```bash
cd /opt/sysadmin/app
sudo git checkout <tag-anterior>      # o v2.2.0-2026-09-16
sudo docker compose up -d --build --force-recreate
sudo docker compose down && sudo docker compose up -d   # si hubo que reiniciar el stack
```

> La BD vive en el volumen `postgres_data`; el backup diario a NAS protege contra pérdida.

---

## 10. Pendientes tras el deploy

- [ ] Renovar cert autofirmado (~dic 2028).
- [ ] Definir credenciales OCS reales en BD o `.env`.
- [ ] OCS 8081: solo abrir en UFW si se expone fuera de la LAN; no exponer el HTTP plano sin TLS.
