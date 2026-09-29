#!/bin/bash
# Instala el cron diario de limpieza de historial.
# Ejecutar con sudo.
set -e

APP_DIR="/opt/sysadmin/app"
LOG_FILE="/var/log/sysadmin-limpiar-historial.log"
CRON_FILE="/etc/cron.d/sysadmin-limpiar-historial"

cat > "$CRON_FILE" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
0 4 * * 0 root cd $APP_DIR && docker exec sysadmin_django python manage.py limpiar_historial --dias 365 --media-dias 30 >> $LOG_FILE 2>&1
EOF

chmod 644 "$CRON_FILE"

# Crear log rotado si no existe
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

systemctl reload cron || service cron reload || true

echo "Cron instalado en $CRON_FILE"
echo "Log: $LOG_FILE"
