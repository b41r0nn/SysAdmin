#!/usr/bin/env bash
# =============================================================================
# patch_ocs_server.sh
#
# Aplica (de forma idempotente) los parches que el contenedor
# `ocsinventory-server` (OCS Inventory NG 2.12.1 sobre Ubuntu 22.04) necesita
# para poder RECIBIR inventarios de los agentes.
#
# Por que hace falta:
#   La imagen del server arranca con el stack Perl del web service roto:
#     1. Falta el modulo Perl `XML::Entities` -> el paquete Debian/Ubuntu
#        `libxml-entities-perl` NO existe en jammy. Se instala desde CPAN.
#     2. Falta `SOAP::Transport::HTTP2` -> `Apache::Ocsinventory::SOAP` lo pide
#        en la rama mod_perl2, y ni la imagen ni `libsoap-lite-perl` lo traen.
#        Se crea como alias de `SOAP::Transport::HTTP::Apache` (que ya tiene la
#        rama mod_perl2) en vez de parchear el modulo de OCS.
#   Sin 1+2 Apache loguea "Can't load SOAP::Transport::HTTP* - Web service will
#   be unavailable" y NO registra ningun inventario.
#
#   3. `html_header.php` tiene un bug de PHP 8 que deja la consola OCS en
#      blanco; se sobreescribe con la copia parcheada de ./patches/.
#
#   4. La imagen trae PHP 8.1 de jammy sin parches de seguridad recientes
#      (php2shell, CVE-2026-109618/109619: RCE sin autenticacion, corregido en
#      8.1.2-1ubuntu2.28). Se actualizan los paquetes php8.1-* instalados desde
#      jammy-security; un --force-recreate vuelve a la version de la imagen.
#
# USO (despues de cada `docker compose up -d --force-recreate` de OCS):
#   bash patch_ocs_server.sh
#
# Verificacion (debe dar 1 equipo por cada agente instalado):
#   OCSUSER=<usuario BD ocsweb>
#   OCSPASS=<clave de ese usuario>
#   docker exec ocsinventory-db mysql -u"$OCSUSER" -p"$OCSPASS" ocsweb \
#     -e "SELECT ID,NAME,OSNAME,LASTCOME FROM hardware;"
#
# URL que usa el agente en el cliente Windows: http://<server>:8081/ocsinventory
# (NO /ocsreports: ese es el path de la web, el receptor XML vive en la raiz)
# =============================================================================
set -euo pipefail

CONTAINER="${OCS_CONTAINER:-ocsinventory-server}"
PERL_LIB="/usr/local/share/perl/5.34.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '[patch-ocs] %s\n' "$*"; }

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    log "ERROR: el contenedor $CONTAINER no existe. Levanta OCS primero."
    exit 1
fi

# --- 1. XML::Entities (no existe como paquete en Ubuntu 22.04) ---------------
if docker exec "$CONTAINER" perl -e 'use XML::Entities;' >/dev/null 2>&1; then
    log "1/4 XML::Entities ya instalado."
else
    log "1/4 instalando XML::Entities desde CPAN..."
    docker exec "$CONTAINER" sh -c \
        'command -v cpanm >/dev/null || apt-get install -y --no-install-recommends cpanminus' >/dev/null
    docker exec "$CONTAINER" cpanm --notest --quiet XML::Entities
    docker exec "$CONTAINER" perl -e 'use XML::Entities;'
    log "1/4 OK."
fi

# --- 2. SOAP::Transport::HTTP2 (lo exige el web service con mod_perl2) --------
if docker exec "$CONTAINER" perl -e 'require SOAP::Transport::HTTP2;' >/dev/null 2>&1; then
    log "2/4 SOAP::Transport::HTTP2 ya disponible."
else
    log "2/4 creando SOAP::Transport::HTTP2..."
    docker exec -i "$CONTAINER" sh -c \
        "mkdir -p $PERL_LIB/SOAP/Transport && cat > $PERL_LIB/SOAP/Transport/HTTP2.pm" <<'PERL'
package SOAP::Transport::HTTP2;
use strict;
require SOAP::Transport::HTTP;
package SOAP::Transport::HTTP2::Apache;
our @ISA = q(SOAP::Transport::HTTP::Apache);
1;
PERL
    log "2/4 OK."
fi

# --- 3. html_header.php (bug PHP 8: consola en blanco) ------------------------
if [ -f "$SCRIPT_DIR/patches/html_header.php" ]; then
    TARGET="$(docker exec "$CONTAINER" sh -c \
        'find /usr/share/ocsinventory-reports -name html_header.php | head -1' | tr -d '\r')"
    if [ -n "$TARGET" ]; then
        docker cp "$SCRIPT_DIR/patches/html_header.php" "$CONTAINER:$TARGET" >/dev/null
        log "3/4 html_header.php parcheado en $TARGET."
    else
        log "3/4 AVISO: no se encontro html_header.php en el contenedor."
    fi
else
    log "3/4 OMITIDO: no existe $SCRIPT_DIR/patches/html_header.php."
fi

# --- 4. Parches de seguridad de PHP (paquetes de jammy-security) -------------
# policy-rc.d (exit 101) ya viene en la imagen: apt no reinicia Apache a mitad.
# Un graceful NO recarga libphp (el PID 1 sigue con la .so vieja "(deleted)"),
# asi que si cambia la version se reinicia el contenedor; docker restart
# conserva el sistema de archivos (los parches 1-3 no se pierden).
log "4/4 actualizando paquetes PHP desde jammy-security..."
PHP_ANTES="$(docker exec "$CONTAINER" dpkg-query -W -f='${Version}' php8.1-common)"
docker exec -i -u 0 -e DEBIAN_FRONTEND=noninteractive "$CONTAINER" sh -s <<'SH'
set -e
pkgs=$(dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' 'php8.1*' 'libapache2-mod-php8.1' \
       | awk '$1=="ii"{print $2}')
apt-get update -qq
apt-get install -y -qq --only-upgrade -o Dpkg::Options::=--force-confold $pkgs >/dev/null
SH
PHP_DESPUES="$(docker exec "$CONTAINER" dpkg-query -W -f='${Version}' php8.1-common)"
log "4/4 OK: PHP $PHP_ANTES -> $PHP_DESPUES."

# --- reload de Apache --------------------------------------------------------
if [ "$PHP_ANTES" != "$PHP_DESPUES" ]; then
    log "PHP cambio: reiniciando $CONTAINER para cargar libphp nueva..."
    docker restart "$CONTAINER" >/dev/null
    sleep 5
else
    docker exec "$CONTAINER" apache2ctl -k graceful
    sleep 2
fi

if docker exec "$CONTAINER" apache2ctl -S 2>&1 | grep -q "Web service will be unavailable"; then
    log "FALLO: el web service de OCS sigue sin cargar. Revisar el error.log."
    exit 1
fi

log "Listo. El receptor de inventarios /ocsinventory queda operativo."
log "Siguiente paso: instalar el agente en un cliente Windows."
log "  $ wget http://$(hostname -I | awk '{print $1}'):8081/download/OcsInventoryAgent.exe"
log "  URL del agente: http://<server>:8081/ocsinventory"
