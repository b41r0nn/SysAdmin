#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# SysAdmin — Backup diario (PostgreSQL + media) → NAS
#
# Fuente canónica del script que setup_server.sh instala en
# /opt/sysadmin/backups/backup.sh. Para actualizar un servidor ya instalado:
#   sudo install -m 750 deploy/backup.sh /opt/sysadmin/backups/backup.sh
#
# Configuración por variables de entorno (o editando este archivo):
#   NAS_IP, NAS_PATH, NAS_USER, RETENCION_DIAS_LOCAL
#   BACKUP_ENV_PASSPHRASE → clave para cifrar el respaldo del .env (obligatoria
#   para respaldar la clave del vault; sin ella NO se respalda el .env).
#
# Uso: sudo bash backup.sh
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Configuración ──────────────────────────────────────────────────────────────
NAS_IP="${NAS_IP:-192.168.1.XXX}"         # ← IP del NAS
NAS_PATH="${NAS_PATH:-/backups/sysadmin}" # ← ruta destino en el NAS
NAS_USER="${NAS_USER:-backup_user}"       # ← usuario del NAS
RETENCION_DIAS_LOCAL="${RETENCION_DIAS_LOCAL:-7}"

APP_DIR="/opt/sysadmin/app"
BACKUP_DIR="/opt/sysadmin/backups"
DB_CONTAINER="sysadmin_db"
DB_USER="sysadmin_user"

FECHA="$(date +%Y-%m-%d_%H-%M)"
BACKUP_FILE="sysadmin_backup_${FECHA}.tar.gz"
ENV_FILE="sysadmin_env_${FECHA}.tar.gz.enc"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

mkdir -p "${BACKUP_DIR}"
cd "${BACKUP_DIR}"

log "Iniciando backup ${FECHA}"

# ── 1. Dump de PostgreSQL ──────────────────────────────────────────────────────
# Sin `|| true`: si el dump falla, el script aborta y el cron avisa.
DUMP="${BACKUP_DIR}/db_dump_${FECHA}.sql"
docker exec "${DB_CONTAINER}" pg_dumpall -U "${DB_USER}" > "${DUMP}"
if [ ! -s "${DUMP}" ]; then
    log "ERROR: el dump de PostgreSQL salió vacío."
    exit 1
fi

# ── 2. Empaquetar DB + media (SIN el .env) ─────────────────────────────────────
# El .env NO va aquí: contiene PASSWORDS_ENCRYPTION_KEY y, junto al dump,
# permitiría descifrar todo el vault. Se respalda aparte y cifrado (paso 3).
tar -czf "${BACKUP_FILE}" \
    "${DUMP}" \
    -C "${APP_DIR}/backend" media
tar -tzf "${BACKUP_FILE}" >/dev/null   # verificar integridad del tar
rm -f "${DUMP}"

# ── 3. Respaldo del .env (clave del vault) separado y cifrado ──────────────────
if [ -f "${APP_DIR}/.env" ]; then
    if [ -n "${BACKUP_ENV_PASSPHRASE:-}" ]; then
        tar -czf - -C "${APP_DIR}" .env | \
            openssl enc -aes-256-cbc -pbkdf2 -salt \
                -pass "pass:${BACKUP_ENV_PASSPHRASE}" -out "${ENV_FILE}"
        log "Clave/.env cifrado en ${ENV_FILE} (guárdalo aparte del backup)."
    else
        log "ADVERTENCIA: BACKUP_ENV_PASSPHRASE no definido; NO se respalda el .env."
        log "             Guarda PASSWORDS_ENCRYPTION_KEY por separado (en un gestor"
        log "             de secretos). Sin esa clave el vault es irrecuperable."
        ENV_FILE=""
    fi
fi

# ── 4. Enviar al NAS (sin --delete: el NAS conserva historial) ─────────────────
if [ "${NAS_IP}" != "192.168.1.XXX" ]; then
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
