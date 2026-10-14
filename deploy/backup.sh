#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# SysAdmin — Backup diario (PostgreSQL + media) → NAS
#
# Fuente canónica del script que setup_server.sh instala en
# /opt/sysadmin/backups/backup.sh. Para actualizar un servidor ya instalado:
#   sudo install -m 750 deploy/backup.sh /opt/sysadmin/backups/backup.sh
#
# Configuración en /opt/sysadmin/backups/backup.conf (ver deploy/backup.conf.example).
# Las variables de entorno siguen funcionando y tienen prioridad sobre ese archivo:
#   NAS_IP, NAS_PATH, NAS_USER, RETENCION_DIAS_LOCAL
#   BACKUP_ENV_PASSPHRASE → clave para cifrar el respaldo del .env (obligatoria
#   para respaldar la clave del vault; sin ella NO se respalda el .env).
#
# Uso: sudo bash backup.sh
#
# ── Restaurar un backup ───────────────────────────────────────────────────────
# El .tar.gz guarda rutas relativas (db_dump_*.sql y media/). Pasos:
#
#   0. En un host con Docker y el compose de SysAdmin:
#        sudo mkdir -p /opt/sysadmin/restore
#        sudo tar -xzf sysadmin_backup_AAAA-MM-DD_HH-MM.tar.gz -C /opt/sysadmin/restore
#
#   1. Restaurar la base de datos (sobre un volumen vacío o con datos que se
#      quieran reemplazar). `pg_dumpall` recrea roles y bases, así que los
#      errores "role already exists" son esperables si el rol sysadmin_user ya
#      existe:
#        cd /opt/sysadmin/app
#        docker compose down
#        docker volume rm sysadmin_postgres_data   # o el nombre del volumen
#        docker compose up -d db
#        docker exec -i sysadmin_db psql -U sysadmin_user -d postgres \
#            < /opt/sysadmin/restore/db_dump_AAAA-MM-DD_HH-MM.sql
#
#   2. Restaurar media:
#        sudo rsync -a /opt/sysadmin/restore/media/ /opt/sysadmin/app/backend/media/
#
#   3. Restaurar el .env cifrado (necesita la passphrase):
#        export BACKUP_ENV_PASSPHRASE='...'
#        openssl enc -d -aes-256-cbc -pbkdf2 \
#            -in sysadmin_env_AAAA-MM-DD_HH-MM.tar.gz.enc \
#            -pass env:BACKUP_ENV_PASSPHRASE | sudo tar -xzf - -C /opt/sysadmin/app
#      Sin el .env (o sin su clave) el vault de contraseñas es irrecuperable.
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Rutas fijas ───────────────────────────────────────────────────────────────
APP_DIR="/opt/sysadmin/app"
BACKUP_DIR="/opt/sysadmin/backups"
DB_CONTAINER="sysadmin_db"
DB_USER="sysadmin_user"

# ── Capturar entorno ANTES de defaults (tiene prioridad sobre backup.conf) ─────
_env_nas_ip="${NAS_IP:-}"
_env_nas_path="${NAS_PATH:-}"
_env_nas_user="${NAS_USER:-}"
_env_retencion="${RETENCION_DIAS_LOCAL:-}"
_env_pass="${BACKUP_ENV_PASSPHRASE:-}"

# ── backup.conf (optativo, junto al script) ────────────────────────────────────
CONF_FILE="${BACKUP_DIR}/backup.conf"
if [ -f "${CONF_FILE}" ]; then
    # shellcheck source=/dev/null
    . "${CONF_FILE}"
fi

# ── Re-aplicar entorno si estaba definido ──────────────────────────────────────
[ -n "${_env_nas_ip}" ] && NAS_IP="${_env_nas_ip}"
[ -n "${_env_nas_path}" ] && NAS_PATH="${_env_nas_path}"
[ -n "${_env_nas_user}" ] && NAS_USER="${_env_nas_user}"
[ -n "${_env_retencion}" ] && RETENCION_DIAS_LOCAL="${_env_retencion}"
[ -n "${_env_pass}" ] && BACKUP_ENV_PASSPHRASE="${_env_pass}"

# ── Defaults ───────────────────────────────────────────────────────────────────
NAS_IP="${NAS_IP:-}"
NAS_PATH="${NAS_PATH:-/backups/sysadmin}"
NAS_USER="${NAS_USER:-backup_user}"
RETENCION_DIAS_LOCAL="${RETENCION_DIAS_LOCAL:-7}"

FECHA="$(date +%Y-%m-%d_%H-%M)"
BACKUP_FILE="sysadmin_backup_${FECHA}.tar.gz"
ENV_FILE="sysadmin_env_${FECHA}.tar.gz.enc"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

mkdir -p "${BACKUP_DIR}"
cd "${BACKUP_DIR}"

log "Iniciando backup ${FECHA}"

# ── 1. Dump de PostgreSQL ──────────────────────────────────────────────────────
# Sin `|| true`: si el dump falla, el script aborta y el cron avisa.
# El `trap` borra el dump (que contiene datos sensibles) pase lo que pase, incluso
# si el script se corta antes de empaquetarlo.
DUMP="${BACKUP_DIR}/db_dump_${FECHA}.sql"
trap 'rm -f "${DUMP}"' EXIT
docker exec "${DB_CONTAINER}" pg_dumpall -U "${DB_USER}" > "${DUMP}"
if [ ! -s "${DUMP}" ]; then
    log "ERROR: el dump de PostgreSQL salió vacío."
    exit 1
fi

# ── 2. Empaquetar DB + media (SIN el .env) ─────────────────────────────────────
# El .env NO va aquí: contiene PASSWORDS_ENCRYPTION_KEY y, junto al dump,
# permitiría descifrar todo el vault. Se respalda aparte y cifrado (paso 3).
# El dump entra con su nombre relativo (no la ruta absoluta) para que el tar
# se pueda extraer sin dispersar archivos por rutas del host.
tar -czf "${BACKUP_FILE}" \
    -C "${BACKUP_DIR}" "$(basename "${DUMP}")" \
    -C "${APP_DIR}/backend" media
tar -tzf "${BACKUP_FILE}" >/dev/null   # verificar integridad del tar

# ── 3. Respaldo del .env (clave del vault) separado y cifrado ──────────────────
if [ -f "${APP_DIR}/.env" ]; then
    if [ -n "${BACKUP_ENV_PASSPHRASE:-}" ]; then
        # `-pass env:` evita que la passphrase quede visible en `ps`.
        export BACKUP_ENV_PASSPHRASE
        tar -czf - -C "${APP_DIR}" .env | \
            openssl enc -aes-256-cbc -pbkdf2 -salt \
                -pass env:BACKUP_ENV_PASSPHRASE -out "${ENV_FILE}"
        log "Clave/.env cifrado en ${ENV_FILE} (guárdalo aparte del backup)."
    else
        log "ADVERTENCIA: BACKUP_ENV_PASSPHRASE no definido; NO se respalda el .env."
        log "             Guarda PASSWORDS_ENCRYPTION_KEY por separado (en un gestor"
        log "             de secretos). Sin esa clave el vault es irrecuperable."
        ENV_FILE=""
    fi
fi

# ── 4. Enviar al NAS (sin --delete: el NAS conserva historial) ─────────────────
if [ -n "${NAS_IP}" ]; then
    rsync -az "${BACKUP_FILE}" "${NAS_USER}@${NAS_IP}:${NAS_PATH}/"
    if [ -n "${ENV_FILE}" ] && [ -f "${ENV_FILE}" ]; then
        rsync -az "${ENV_FILE}" "${NAS_USER}@${NAS_IP}:${NAS_PATH}/"
    fi
    log "Enviado al NAS ${NAS_IP}:${NAS_PATH}"
else
    log "ADVERTENCIA: NAS_IP sin configurar; el backup queda solo local."
fi

# ── 5. Retención local (el NAS conserva el historial completo) ────────────────
find "${BACKUP_DIR}" -maxdepth 1 -name "sysadmin_backup_*.tar.gz" \
    -mtime +"${RETENCION_DIAS_LOCAL}" -delete
find "${BACKUP_DIR}" -maxdepth 1 -name "sysadmin_env_*.tar.gz.enc" \
    -mtime +"${RETENCION_DIAS_LOCAL}" -delete

log "Backup completado: ${BACKUP_FILE}"
