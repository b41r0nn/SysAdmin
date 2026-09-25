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
    log "1/3 XML::Entities ya instalado."
else
    log "1/3 instalando XML::Entities desde CPAN..."
    docker exec "$CONTAINER" sh -c \
        'command -v cpanm >/dev/null || apt-get install -y --no-install-recommends cpanminus' >/dev/null
    docker exec "$CONTAINER" cpanm --notest --quiet XML::Entities
    docker exec "$CONTAINER" perl -e 'use XML::Entities;'
    log "1/3 OK."
fi

# --- 2. SOAP::Transport::HTTP2 (lo exige el web service con mod_perl2) --------
if docker exec "$CONTAINER" perl -e 'require SOAP::Transport::HTTP2;' >/dev/null 2>&1; then
    log "2/3 SOAP::Transport::HTTP2 ya disponible."
else
    log "2/3 creando SOAP::Transport::HTTP2..."
    docker exec -i "$CONTAINER" sh -c \
        "mkdir -p $PERL_LIB/SOAP/Transport && cat > $PERL_LIB/SOAP/Transport/HTTP2.pm" <<'PERL'
package SOAP::Transport::HTTP2;
use strict;
require SOAP::Transport::HTTP;
package SOAP::Transport::HTTP2::Apache;
our @ISA = q(SOAP::Transport::HTTP::Apache);
1;
PERL
    log "2/3 OK."
fi

# --- 3. html_header.php (bug PHP 8: consola en blanco) ------------------------
if [ -f "$SCRIPT_DIR/patches/html_header.php" ]; then
    TARGET="$(docker exec "$CONTAINER" sh -c \
        'find /usr/share/ocsinventory-reports -name html_header.php | head -1' | tr -d '\r')"
    if [ -n "$TARGET" ]; then
        docker cp "$SCRIPT_DIR/patches/html_header.php" "$CONTAINER:$TARGET" >/dev/null
        log "3/3 html_header.php parcheado en $TARGET."
    else
        log "3/3 AVISO: no se encontro html_header.php en el contenedor."
    fi
else
    log "3/3 OMITIDO: no existe $SCRIPT_DIR/patches/html_header.php."
fi

# --- reload de Apache --------------------------------------------------------
docker exec "$CONTAINER" apache2ctl -k graceful
sleep 2

if docker exec "$CONTAINER" apache2ctl -S 2>&1 | grep -q "Web service will be unavailable"; then
    log "FALLO: el web service de OCS sigue sin cargar. Revisar el error.log."
    exit 1
fi

log "Listo. El receptor de inventarios /ocsinventory queda operativo."
log "Siguiente paso: instalar el agente en un cliente Windows."
log "  $ wget http://$(hostname -I | awk '{print $1}'):8081/download/OcsInventoryAgent.exe"
log "  URL del agente: http://<server>:8081/ocsinventory"
