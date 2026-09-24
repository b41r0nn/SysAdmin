#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# SysAdmin
# Script de preparación del Ubuntu Server (convive con otros servicios en el host)
# Ejecutar como: sudo bash setup_server.sh
#
# NOTA: idempotente y NO destructivo. Detecta lo ya instalado y NO toca
# las reglas UFW ni los contenedores de otros servicios (p.ej. Hikvision
# Extractor: 80/8000). Solo agrega lo que SysAdmin necesita (6060/6061).
# ═══════════════════════════════════════════════════════════════════════════════

set -e  # Detener si cualquier comando falla

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║       SysAdmin — Setup Ubuntu Server                ║"
echo "║       Empresa                                        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ─── 1. Actualizar el sistema ─────────────────────────────────────────────────
echo "📦 [1/7] Actualizando el sistema..."
apt-get update -qq && apt-get upgrade -y -qq
echo "✅ Sistema actualizado."

# ─── 2. Instalar utilidades base ──────────────────────────────────────────────
echo "🔧 [2/7] Instalando utilidades base..."
apt-get install -y -qq \
    curl \
    wget \
    git \
    ufw \
    rsync \
    htop \
    nano \
    unzip \
    ca-certificates \
    gnupg \
    lsb-release \
    apt-transport-https
echo "✅ Utilidades instaladas."

# ─── 3. Instalar Docker (solo si no está) ─────────────────────────────────────
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "🐳 [3/7] Docker ya está instalado — se omite la instalación:"
    echo "   ✅ $(docker --version) / $(docker compose version)"
else
    echo "🐳 [3/7] Instalando Docker..."

    # Agregar clave GPG oficial de Docker
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Agregar repositorio Docker
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Instalar Docker Engine + Compose
    apt-get update -qq
    apt-get install -y -qq \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin

    # Habilitar Docker al arranque
    systemctl enable docker
    systemctl start docker

    echo "✅ Docker instalado: $(docker --version)"
    echo "✅ Docker Compose: $(docker compose version)"
fi

# ─── 4. Configurar usuario para Docker (sin sudo) ─────────────────────────────
echo "👤 [4/7] Configurando permisos Docker..."
SUDO_USER_NAME="${SUDO_USER:-$USER}"
if [ -n "$SUDO_USER_NAME" ] && [ "$SUDO_USER_NAME" != "root" ]; then
    usermod -aG docker "$SUDO_USER_NAME"
    echo "✅ Usuario '$SUDO_USER_NAME' agregado al grupo docker."
    echo "   ⚠️  Cierra y vuelve a abrir la sesión SSH para que tome efecto."
else
    echo "   ℹ️  Ejecutando como root, no se agrega a grupo."
fi

# ─── 5. Configurar Firewall UFW (respetando reglas de otros servicios) ────────
echo "🔒 [5/7] Asegurando firewall (se respetan reglas existentes de otros servicios)..."
ufw default deny incoming
ufw default allow outgoing
# Reglas de SysAdmin (SÓLO se agregan; las de otros servicios, p.ej. Hikvision
# 80/3000/8000, ya existentes NO se tocan):
ufw allow ssh          # Puerto 22 — acceso SSH
ufw allow 6060/tcp     # HTTPS interno (nginx) — app web SysAdmin
ufw allow 6061/tcp     # HTTP → redirect 301 a HTTPS
if ! ufw status | grep -q "Status: active"; then
    ufw --force enable
fi
echo "✅ Firewall asegurado. Reglas activas:"
ufw status numbered

# ─── 6. Configurar rsync hacia NAS ───────────────────────────────────────────
echo "💾 [6/7] Preparando directorio de backups..."
mkdir -p /opt/sysadmin/backups
chmod 750 /opt/sysadmin/backups

# ─── 7. Certificado autofirmado (HTTPS interno) ──────────────────────────────
echo "🔐 [7/7] Generando certificado autofirmado..."
mkdir -p /opt/sysadmin/app/nginx/certs
if [ ! -f /opt/sysadmin/app/nginx/certs/server.crt ]; then
    openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
        -keyout /opt/sysadmin/app/nginx/certs/server.key \
        -out /opt/sysadmin/app/nginx/certs/server.crt \
        -subj "/CN=192.168.1.250"
    echo "✅ Certificado generado (CN=192.168.1.250, 825 días)."
else
    echo "   ℹ️  Certificado ya existe, no se regenera."
fi

# Script de backup diario
cat > /opt/sysadmin/backups/backup.sh << 'BACKUP_SCRIPT'
#!/bin/bash
# Backup automático SysAdmin → NAS
# ─────────────────────────────────────────────
# CONFIGURA ESTAS VARIABLES:
NAS_IP="192.168.1.XXX"          # ← IP de tu NAS
NAS_PATH="/backups/sysadmin"    # ← Ruta en la NAS
NAS_USER="backup_user"          # ← Usuario en la NAS
# ─────────────────────────────────────────────

FECHA=$(date +%Y-%m-%d_%H-%M)
BACKUP_DIR="/opt/sysadmin/backups"
BACKUP_FILE="sysadmin_backup_${FECHA}.tar.gz"

echo "[$(date)] Iniciando backup..."

# Exportar base de datos PostgreSQL
docker exec sysadmin_db pg_dumpall -U sysadmin_user > "${BACKUP_DIR}/db_dump.sql"

# Comprimir DB + media (actas, fotos)
tar -czf "${BACKUP_DIR}/${BACKUP_FILE}" \
    "${BACKUP_DIR}/db_dump.sql" \
    /opt/sysadmin/media/ 2>/dev/null || true

# Eliminar dump temporal
rm -f "${BACKUP_DIR}/db_dump.sql"

# Enviar a NAS vía rsync
rsync -az --delete \
    "${BACKUP_DIR}/" \
    "${NAS_USER}@${NAS_IP}:${NAS_PATH}/"

# Eliminar backups locales de más de 7 días
find "${BACKUP_DIR}" -name "*.tar.gz" -mtime +7 -delete

echo "[$(date)] Backup completado: ${BACKUP_FILE}"
BACKUP_SCRIPT

chmod +x /opt/sysadmin/backups/backup.sh

# Agregar al cron (2:00 AM todos los días)
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/sysadmin/backups/backup.sh >> /opt/sysadmin/backups/backup.log 2>&1") | crontab -

echo "✅ Script de backup creado en /opt/sysadmin/backups/backup.sh"
echo "   ⚠️  Edita el script y configura la IP y credenciales de tu NAS."

# ─── Resumen final ────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅  Servidor preparado correctamente                ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Próximos pasos:                                     ║"
echo "║  1. Copia el proyecto SysAdmin a /opt/sysadmin/app   ║"
echo "║  2. Edita el archivo .env con tus credenciales       ║"
echo "║     (ver CHECKLIST_DEPLOY.md)                        ║"
echo "║  3. Edita backup.sh con la IP y usuario de tu NAS    ║"
echo "║  4. Ejecuta: docker compose up -d --build            ║"
echo "║  5. Ejecuta: docker exec sysadmin_django             ║"
echo "║             python manage.py createsuperuser         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
