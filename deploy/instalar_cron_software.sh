#!/bin/bash
# Instala el cron de lectura de software y muestra cómo verificarlo.
#
# Se instala como root porque /etc/cron.d es del sistema. El script corre como
# `sistemas` y su salida va a /var/log/sysadmin-software-sync.log.
#
#   sudo bash deploy/instalar_cron_software.sh
set -euo pipefail

ORIGEN="$(cd "$(dirname "$0")" && pwd)/sysadmin-sincronizar-software.cron"
DESTINO="/etc/cron.d/sysadmin-sincronizar-software"
LOG="/var/log/sysadmin-software-sync.log"

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

# El log lo escribe el propio cron, que corre como root porque `docker exec` lo
# necesita. Se prepara vacío para que el primer fallo sea del comando y no de
# un archivo inexistente.
touch "$LOG"
chmod 644 "$LOG"

install -m 644 -o root -g root "$ORIGEN" "$DESTINO"

echo "Instalado: $DESTINO"
echo "Log:        $LOG"
echo ""
echo "Corre una vez al dia, a las 03:07. Como el agente OCS reporta cada hora,"
echo "la base puede quedar hasta 24h por detras de lo ultimo que reporto cada"
echo "equipo. Para inventario alcanza."
echo ""
echo "Para ver el log (solo lectura, no necesita sudo):"
echo "  tail -f $LOG"
echo ""
echo "Para probarlo ya sin esperar a las 03:07:"
echo "  sudo docker exec sysadmin_django python manage.py sincronizar_software --verbose --pausa 2"
echo ""
echo "Para cambiar la frecuencia, edita la ultima linea de $DESTINO"
echo "y recargalo con: sudo systemctl reload cron"
echo ""
echo "Para quitarlo:"
echo "  sudo rm $DESTINO"
