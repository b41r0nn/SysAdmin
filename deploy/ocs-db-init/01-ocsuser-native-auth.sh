#!/bin/bash
# Deja ocsuser en mysql_native_password al inicializar la base de OCS.
#
# Por que: MySQL 8 crea MYSQL_USER con caching_sha2_password. Sobre TCP sin
# SSL ese plugin exige intercambio de clave RSA, y el DBD::mysql de Perl del
# contenedor ocsinventory-server no lo soporta -> la API /ocsapi/v1 responde
# 500 y el receptor /ocsinventory tambien. El panel PHP no lo nota porque
# mysqli si sabe hacerlo.
#
# MySQL corre esto solo cuando el datadir esta vacio (ver
# https://github.com/docker-library/docs/blob/master/mysql/README.md).
# Si borras el volumen y reconstruyes la BD, esto se aplica solo.
#
# NO lleva la contrasena escrita: la toma de $MYSQL_PASSWORD, que el entrypoint
# de MySQL expone desde el docker-compose.
#
# Montar en: /docker-entrypoint-initdb.d/01-ocsuser-native-auth.sh
set -uo pipefail

# MySQL ejecuta los .sh de /docker-entrypoint-initdb.d/ con "./f" si no tiene
# bit de ejecucion, y con "f" si lo tiene. Si nos sources, cualquier `exit`
# cortaria el arranque de MySQL entero. Por eso todo corre en un subshell.
(
set -e

log() { echo "[ocs-init] $*"; }

if [ -z "${MYSQL_USER:-}" ] || [ -z "${MYSQL_PASSWORD:-}" ]; then
    log "ERROR: MYSQL_USER/MYSQL_PASSWORD no definidos. Nada que hacer."
    exit 1
fi

# Si el servidor ya no ofrece el plugin (MySQL 8.4+ lo elimino), avisar en
# lugar de fallar en silencio: la API quedaria rota y nadie lo veria aqui.
if ! mysql --user=root --password="${MYSQL_ROOT_PASSWORD:-}" \
        -N -B -e "SELECT PLUGIN_NAME FROM information_schema.PLUGINS WHERE PLUGIN_NAME='mysql_native_password' AND PLUGIN_STATUS='ACTIVE';" \
        2>/dev/null | grep -q mysql_native_password; then
    log "AVISO: mysql_native_password no esta activo en este MySQL."
    log "       La API /ocsapi/v1 y el receptor /ocsinventory quedaran rotos."
    log "       Ver OCS_INVENTORY_SETUP.md -> 'caching_sha2_password'."
    exit 0
fi

actual=$(mysql --user=root --password="${MYSQL_ROOT_PASSWORD:-}" -N -B \
    -e "SELECT plugin FROM mysql.user WHERE user='${MYSQL_USER}' AND host='%';" 2>/dev/null || true)

if [ "${actual}" = "mysql_native_password" ]; then
    log "OK: ${MYSQL_USER} ya usa mysql_native_password. Sin cambios."
    exit 0
fi

log "Cambiando ${MYSQL_USER} de '${actual:-desconocido}' a mysql_native_password..."
mysql --user=root --password="${MYSQL_ROOT_PASSWORD:-}" \
    -e "ALTER USER '${MYSQL_USER}'@'%' IDENTIFIED WITH mysql_native_password BY '${MYSQL_PASSWORD}'; FLUSH PRIVILEGES;"

nuevo=$(mysql --user=root --password="${MYSQL_ROOT_PASSWORD:-}" -N -B \
    -e "SELECT plugin FROM mysql.user WHERE user='${MYSQL_USER}' AND host='%';" 2>/dev/null || true)

if [ "${nuevo}" = "mysql_native_password" ]; then
    log "Listo. Verificado: ${MYSQL_USER} usa ${nuevo}."
else
    log "ERROR: no se pudo aplicar. El plugin sigue en '${nuevo:-?}'."
    exit 1
fi

)
# Fin del subshell. Si nos|sourcearon, el `exit 1` de arriba solo salio de aqui.
