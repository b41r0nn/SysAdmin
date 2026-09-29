#!/bin/bash
# Instala los crons de notificaciones y emails de SysAdmin.
#
#   sudo bash deploy/instalar_cron_notificaciones.sh
set -euo pipefail

ORIGEN="$(cd "$(dirname "$0")" && pwd)/sysadmin-notificaciones.cron"
DESTINO="/etc/cron.d/sysadmin-notificaciones"

if [ "$(id -u)" -ne 0 ]; then
    echo "Corre esto con sudo:  sudo bash $0"
    exit 1
fi

if [ ! -f "$ORIGEN" ]; then
    echo "No se encuentra el archivo de cron en: $ORIGEN"
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx sysadmin_django; then
    echo "El contenedor sysadmin_django no está arriba. Levántalo primero."
    exit 1
fi

# Preparar logs vacíos para que el primer fallo sea del comando y no del archivo.
touch /var/log/sysadmin-notificaciones.log
chmod 644 /var/log/sysadmin-notificaciones.log
touch /var/log/sysadmin-emails.log
chmod 644 /var/log/sysadmin-emails.log

install -m 644 -o root -g root "$ORIGEN" "$DESTINO"

echo "Instalado: $DESTINO"
echo "Logs:      /var/log/sysadmin-notificaciones.log"
echo "           /var/log/sysadmin-emails.log"
echo ""
echo "Para ver logs:"
echo "  tail -f /var/log/sysadmin-notificaciones.log"
echo "  tail -f /var/log/sysadmin-emails.log"
echo ""
echo "Para probar ahora:"
echo "  sudo docker exec sysadmin_django python manage.py generar_notificaciones_mantenimiento"
echo "  sudo docker exec sysadmin_django python manage.py enviar_notificaciones_email"
echo ""
echo "Recargar cron:  sudo systemctl reload cron"
echo "Para quitarlo:  sudo rm $DESTINO"
