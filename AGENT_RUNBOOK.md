# SysAdmin · Runbook operativo de producción

> Estado al 2026-09-24 (deploy completo). Referencia compacta para el arqui/agente.
> El histórico detallado vive en `SYSADMIN_HANDOFF.md`; aquí solo lo que se toca en operación.

## Ambiente

- Servidor: `sistemas@192.168.1.250` · Ubuntu Server 22.04 · proyecto en `/opt/sysadmin/app` (Docker Compose).
- Web: `https://192.168.1.250:6060` (HTTPS) · `http://192.168.1.250:6061` (301 → https). Cert autofirmado CN=192.168.1.250.
- Contenedores: `sysadmin_db` (postgres:15-alpine) · `sysadmin_django` (django 4.2 / python 3.11, gunicorn, axes) · `sysadmin_nginx`. Hikvision corre aparte en sus propios contenedores/redes (no se toca).
- `.env` en `/opt/sysadmin/app/.env` (`DEBUG=False`). Repo local = fuente · servidor = copia vía `rsync` (excluye `venv/`, `backend/media`, `tmp_scratch*`).

## Accesos

- Admin Django: `https://192.168.1.250:6060/accounts/login/` (login = `accounts.CustomUser`; superusuarios creados en deploy).
- Consola: `docker exec -it sysadmin_django python manage.py shell`.
- DB: `docker exec -it sysadmin_db psql -U sysadmin_user -d sysadmin_db`.

## Diagnóstico rápido

```bash
# estado contenedores
sudo docker compose -f /opt/sysadmin/app/docker-compose.yml ps
# salud
sudo docker inspect --format '{{.Name}} {{.State.Health.Status}}' sysadmin_db sysadmin_django sysadmin_nginx
# logs
sudo docker logs --tail 50 sysadmin_django
# HTTPS real (con X-Forwarded-Proto para evitar redirect loop)
curl -sk -H 'X-Forwarded-Proto: https' -o /dev/null -w '%{http_code}\n' https://192.168.1.250:6060/accounts/login/
```

## Notas de seguridad / fixes aplicados (importante)

- `base.py` define `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` — sin esto, con `SECURE_SSL_REDIRECT=True` detrás de nginx → **redirect loop** → healthcheck Django falla → compose aborta.
- El healthcheck de `sysadmin_django` manda `X-Forwarded-Proto: https` en la request (requerido, ver `docker-compose.yml`).
- Login: django-axes (5 intentos fallidos → lockout 1h) · auditoría vía signals · mensajes de error genéricos.

## Pendientes

1. **Backup a NAS** — `/opt/sysadmin/backups/backup.sh` existe sin destino/cron configurado. Falta IP/usuario/ruta del NAS.
2. **OCS/Yule** — endpoint no configurado. Los logs muestran `Error OCS: OCS no está configurado`. Falta endpoint OCSP + credenciales.
3. **Commitear fixes del deploy** — los cambios (`base.py`, `docker-compose.yml`, excludes) quedan en el working tree local, sin commitear (regla AGENTS.md).
