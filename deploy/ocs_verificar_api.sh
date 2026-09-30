#!/bin/bash
# Verifica (y repara) que la API de OCS y el receptor /ocsinventory puedan
# hablar con la base de datos. Idempotente: se puede correr las veces que haga
# falta, solo cambia lo que este mal.
#
#   bash deploy/ocs_verificar_api.sh            # solo diagnostica
#   bash deploy/ocs_verificar_api.sh --arreglar # repara lo que encuentre
#
# Por que existe: /docker-entrypoint-initdb.d/ solo corre cuando el datadir de
# MySQL esta vacio. Si alguien hace un ALTER USER a mano, o sube MySQL a 8.4+
# (donde mysql_native_password ya no existe), la API vuelve a 500 sin que nada
# avise. Este script es la red de seguridad.
#
# Los dos fallos que vigila:
#   1. ocsuser con caching_sha2_password -> el DBD::mysql de Perl no autentica.
#   2. Los .conf de Apache con una contrasena distinta a la del compose. Los
#      genera la imagen con 'if [ ! -f ... ]', y viven en el volumen
#      httpdconfdata, asi que una rotacion de contrasena NO llega a ellos.
set -uo pipefail

ARREGLAR=0
[ "${1:-}" = "--arreglar" ] && ARREGLAR=1

COMPOSE="${OCS_COMPOSE:-/home/sistemas/ocs/OCSInventory-Docker-Image/2.12.1/docker-compose.yml}"
SERVER="${OCS_SERVER:-ocsinventory-server}"
DB="${OCS_DB:-ocsinventory-db}"
API="${OCS_API_URL:-http://192.168.1.250:8081}"
CAMBIOS=0

rojo() { echo "  [FALLA] $*"; }
verde() { echo "  [OK]    $*"; }
aviso() { echo "  [AVISO] $*"; }

if [ ! -f "$COMPOSE" ]; then
    echo "No encuentro el compose en $COMPOSE"
    echo "Indica otro con: OCS_COMPOSE=/ruta/docker-compose.yml bash $0"
    exit 1
fi

# La contrasena se lee del compose, que es la fuente de verdad. No va escrita
# en este script.
PASS=$(grep -E '^\s*OCS_DB_PASS\s*:' "$COMPOSE" | head -1 | sed 's/.*:\s*//' | tr -d '"'"'"' \r')
ROOTPASS=$(grep -E '^\s*MYSQL_ROOT_PASSWORD\s*:' "$COMPOSE" | head -1 | sed 's/.*:\s*//' | tr -d '"'"'"' \r')

if [ -z "$PASS" ]; then
    echo "No pude leer OCS_DB_PASS de $COMPOSE"
    exit 1
fi

mysql_root() {
    docker exec "$DB" mysql -uroot -p"$ROOTPASS" -N -B -e "$1" 2>/dev/null | grep -v '^mysql: \[Warning\]'
}

echo "=============================================================="
echo " OCS · API y receptor contra la base de datos"
echo " compose: $COMPOSE"
echo " modo:    $([ $ARREGLAR -eq 1 ] && echo 'reparar' || echo 'solo diagnosticar')"
echo "=============================================================="

# --- 1. plugin de autenticacion -------------------------------------------
echo
echo "1. Plugin de autenticacion de ocsuser"
plugin=$(mysql_root "SELECT plugin FROM mysql.user WHERE user='ocsuser' AND host='%';" | head -1)
if [ -z "$plugin" ]; then
    rojo "No existe el usuario ocsuser@%"
elif [ "$plugin" = "mysql_native_password" ]; then
    verde "ocsuser usa mysql_native_password"
else
    rojo "ocsuser usa '$plugin' -> el DBD::mysql de Perl no autentica (API 500)"
    if [ $ARREGLAR -eq 1 ]; then
        mysql_root "ALTER USER 'ocsuser'@'%' IDENTIFIED WITH mysql_native_password BY '$PASS'; FLUSH PRIVILEGES;" >/dev/null
        nuevo=$(mysql_root "SELECT plugin FROM mysql.user WHERE user='ocsuser' AND host='%';" | head -1)
        if [ "$nuevo" = "mysql_native_password" ]; then
            verde "reparado -> mysql_native_password"; CAMBIOS=1
        else
            rojo "no se pudo reparar (sigue en '$nuevo')"
        fi
    fi
fi

# --- 2. contrasena en los .conf de Apache ---------------------------------
echo
echo "2. Contrasena en los .conf de Apache (volumen httpdconfdata)"
# El password va a un sed como replacement, asi que no puede llevar | ni &
if printf '%s' "$PASS" | grep -q '[|&]'; then
    echo "La contrasena del compose lleva | o & y este script no la maneja."
    echo "Revisa a mano: /etc/apache2/conf-available/ en $SERVER"
    exit 1
fi

# Los dos .conf no usan el mismo formato:
#   z-ocsinventory-server.conf   ->  PerlSetVar OCS_DB_PWD P@assword1
#   zz-ocsinventory-restapi.conf ->  $ENV{OCS_DB_PWD} = 'P@assword1';
# Se toma el primer token no alfanumerico que sigue al nombre. El archivo se
# trae con `cat` y se parsea en bash: meter sed dentro de docker exec habria
# que anidar comillas en tres niveles y es fragil.
pwd_de_conf() {
    docker exec "$SERVER" cat "/etc/apache2/conf-available/$1" 2>/dev/null \
        | sed -n "s/.*OCS_DB_PWD[^A-Za-z0-9]*['\"]\{0,1\}\([^'\"]*\)['\"]\{0,1\}.*/\1/p" \
        | head -1 | tr -d ' \r'
}

for f in z-ocsinventory-server.conf zz-ocsinventory-restapi.conf; do
    dentro=$(pwd_de_conf "$f")
    if [ -z "$dentro" ]; then
        aviso "$f: no encontre OCS_DB_PWD (revisar a mano)"
    elif [ "$dentro" = "$PASS" ]; then
        verde "$f: coincide con el compose"
    else
        rojo "$f: usa '$dentro' pero el compose dice '$PASS' -> 500 en la API"
        if [ $ARREGLAR -eq 1 ]; then
            docker exec "$SERVER" sed -i "s|$dentro|$PASS|g" "/etc/apache2/conf-available/$f" 2>/dev/null
            despues=$(pwd_de_conf "$f")
            if [ "$despues" = "$PASS" ]; then
                verde "$f: reparado"; CAMBIOS=1
            else
                rojo "$f: no se pudo reparar (queda '$despues')"
            fi
        fi
    fi
done

# --- 3. recarga de Apache si hizo falta ----------------------------------
if [ "$CAMBIOS" -eq 1 ]; then
    echo
    echo "3. Recarga de Apache"
    if docker exec "$SERVER" apachectl -t >/dev/null 2>&1; then
        docker exec "$SERVER" apachectl -k graceful >/dev/null 2>&1
        sleep 4
        verde "recargado (graceful)"
    else
        rojo "apachectl -t fallo, NO se recarga. Revisa la sintaxis a mano:"
        docker exec "$SERVER" apachectl -t 2>&1 | tail -5
    fi
else
    echo
    echo "3. Recarga de Apache: no hizo falta"
fi

# --- 4. pruebas de humo ---------------------------------------------------
echo
echo "4. Pruebas de humo"
api=$(curl -s -o /dev/null -w '%{http_code}' -u "sistemas:$PASS" "$API/ocsapi/v1/computers?limit=1" 2>/dev/null)
[ "$api" = "200" ] && verde "API /ocsapi/v1/computers -> 200" || rojo "API /ocsapi/v1/computers -> ${api:-sin respuesta}"

panel=$(curl -s -o /dev/null -w '%{http_code}' "$API/ocsreports/" 2>/dev/null)
[ "$panel" = "200" ] && verde "panel /ocsreports/ -> 200" || rojo "panel /ocsreports/ -> ${panel:-sin respuesta}"

recep=$(docker logs --since 24h "$SERVER" 2>&1 | grep 'POST /ocsinventory' | grep -v curl | tail -1 | grep -o '" [0-9][0-9][0-9] ' | tr -d '" ')
if [ -n "$recep" ]; then
    [ "$recep" = "200" ] && verde "ultimo POST de agente -> 200" || rojo "ultimo POST de agente -> $recep (los agentes no estan entrando)"
else
    aviso "sin POST de agente en 24h (el agente reporta cada PROLOG_FREQ horas)"
fi

# --- 5. diagnostico si algo falla ----------------------------------------
if [ "$api" != "200" ]; then
    echo
    echo "5. Ultimos errores del contenedor"
    docker logs --tail 200 "$SERVER" 2>&1 | grep -i -e 'ApiCommon' -e 'Access denied' -e 'caching_sha2' | tail -5
fi

echo
echo "=============================================================="
if [ "$api" = "200" ] && [ "$panel" = "200" ]; then
    echo " Resultado: API y panel operativos"
else
    echo " Resultado: HAY ALGO ROTO. Arriba esta el motivo."
fi
echo "=============================================================="
