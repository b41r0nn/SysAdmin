# Informe técnico: OCS Inventory NG 2.12.1 no registra equipos y Yule no muestra inventario

**Fecha:** 2026-09-25
**Servidor:** 192.168.1.250 (Ubuntu Server 22.04, `sistemas@ubuntuserver`)
**Solicitante:** Sistemas (REDIHOS) · **Destinatario:** Arquitectura / Analista
**Estado:** **RESUELTO (2026-09-28).** Un agente real reporta a OCS y Yule muestra el inventario completo. Causa raíz: el agente no apuntaba a `/ocsinventory`. El `500` con XML sintético no era un defecto del servidor. Ver sección 0.

---

## 0. Resolución (2026-09-28)

### 0.1 Causa raíz

El agente de inventario estaba configurado contra una URL equivocada. OCS expone
tres rutas distintas que no son intercambiables:

| Ruta | Propósito | Configurar en |
|---|---|---|
| `/ocsinventory` | **receptor** de inventarios (el agente debe apuntar aquí) | agente Windows / Linux |
| `/ocsapi/v1` | API JSON que consume Yule | Yule (`/yule/configuracion/`) |
| `/ocsreports/` | panel web | navegador |

El agente apuntaba a `/ocsreports` o a `/ocsapi/v1`, por lo que nunca hubo un
`POST` al receptor. **No era un fallo del servidor OCS**: no había tráfico que
ingerir. Con la URL corregida, el primer inventario entró sin tocar nada del lado
servidor más allá de los parches ya aplicados.

Consecuencia sobre el `500`: el XML de prueba manual no era un inventario válido
(venía con la sección `hardware` vacía), por eso creaba la fila a medias y
fallaba al digerir. **Era un artefacto de la prueba, no un bug de OCS.** Las
hipótesis H1-H13 y el test de descarte de H14 quedan retiradas.

### 0.2 Verificación end-to-end

| Verificación | Resultado |
|---|---|
| `POST /ocsinventory` (agente real) | `200 OK` |
| Access log Apache | `28/Sep/2026:22:27:57 +0200` · `OCS-NG_WINDOWS_AGENT_v2.11.0.1` |
| Fila en OCS `hardware` | ID `3` · `W11F35F` · Windows 11 Pro `10.0.26200` |
| Secciones OCS | `bios` 1 · `networks` 48 · `software` 122 |
| `GET /ocsapi/v1/computers?limit=1` | `200` con el equipo indexado por ID |
| Yule `sync_ocs --force` | 1 detectados · 1 nuevos · 0 desaparecidos |
| Tests SysAdmin | 335/335 local · 44/44 en el server |

### 0.3 Bugs del lado Yule encontrados al mapear el JSON real

Al contrastar contra la respuesta real de OCS 2.12 aparecieron cinco campos que
llegaban vacíos o incorrectos. Todos estaban en el parser, no en los datos:

| Campo | Síntoma | Causa | Corrección |
|---|---|---|---|
| `serial_bios` | vacío | `bios` llega como **lista** y el serial está en `SSN`, no en `SN` | `_section()` normaliza listas; se lee `SSN` con fallback a `SN`/`MSN` |
| `procesador` | vacío | `hardware.PROCESSORS` es la frecuencia en MHz (entero `1300`), no el nombre | se lee `hardware.PROCESSORT`; fallback a `cpus[0].TYPE` |
| `ip_address` | vacío | se tomaba la 1.ª de 48 interfaces, que es virtual y no tiene IP | se usa `hardware.IPADDR` y se cruza con la interfaz que la tiene |
| `mac_address` | `00:09:0F:AA:00:01` | esa MAC es de la interfaz virtual del firewall, inservible para cruzar contra el inventario local | se elige la MAC de la interfaz con la IP real (`E8:CF:83:0A:8C:0E`) |
| `usuario_dominio` | vacío | OCS no manda `user` en la raíz: va en `hardware.USERID` + `hardware.WORKGROUP` | se compone `redihossas.local\Sistemas` |

Dos defectos adicionales de la misma causa raíz:

- **Software vacío en todos los equipos (el más grave).** `/computer/{id}`
  devuelve el software bajo la **clave literal vacía**:
  `{"3": {"": [{NAME, VERSION, PUBLISHER}, ...]}}`. `get_software()` buscaba
  la clave `"software"` y devolvía siempre `[]`. Ahora recorre la respuesta y
  toma la primera lista de filas con nombre y versión, sin confundirla con
  `memories`, `monitors` y demás.
- **`ultimo_reporte_ocs` con 5 horas de desfase.** OCS escribe `LASTCOME` con
  `NOW()` evaluado por la base de datos, que corre en **UTC**, y lo devuelve sin
  zona. El access log marcaba `22:27:57 +0200` y `LASTCOME` traía `20:27:57`:
  el mismo instante. Interpretarlo como hora local (America/Bogota) lo movía a
  `2026-09-29 01:27:57+00`. Ahora se interpreta como UTC.

Estado verificado tras el despliegue: `usuario_dominio` `redihossas.local\Sistemas`,
`serial_bios` `F35F284`, `mac_address` `E8:CF:83:0A:8C:0E`, `ip_address`
`192.168.1.137`, `procesador` `13th Gen Intel(R) Core(TM) i5-1335U`,
`almacenamiento_total_gb` `476`, `ultimo_reporte_ocs` `2026-09-28 20:27:57+00`.

### 0.4 Pendientes que quedan abiertos

1. `OCS_OPT_LOGLEVEL` está en `512` (subió para diagnosticar). **Volver a `0`.**
2. La contraseña de la base de datos de OCS sigue siendo la de fábrica, que es
   pública. **Rotarla.**
3. Los parches Perl/PHP del contenedor son efímeros: se pierden con
   `--force-recreate` y hay que correr `patch_ocs_server.sh` otra vez.
4. Backup de SysAdmin al NAS: falta definir destino.

---

## 1. Resumen ejecutivo

El servidor de OCS Inventory NG 2.12.1 (contenedor Docker) **arranca con su
"receptor de inventarios" deshabilitado** por dos módulos de Perl ausentes en la
imagen oficial para Ubuntu 22.04. Esto se corrigió a mano. Sin embargo:

1. **Sigue sin entrar ningún equipo.** El panel web de OCS muestra `Total: 0
   equipos detectados` y la tabla `hardware` está vacía. No se ha podido
   confirmar que un agente real (Windows) reporte.
2. **Hay un error 500 en la ingesta** que no se ha logrado explicar: una prueba
   manual con XML sintético crea la fila en `hardware` pero **todos los campos
   quedan en `NULL`**, lo que sugiere un problema de esquema o de formato del
   payload que puede afectar también a los agentes reales.
3. La **integración Yule (SysAdmin → OCS)** quedó funcional y además se
   corrigieron dos bugs del cliente quehacían que Yule mostrara 0 equipos
   incluso con datos presentes en OCS.

Conclusión: la parte de SysAdmin está resuelta; **el lado OCS requiere análisis
adicional** antes de considerarlo estable.

---

## 2. Entorno

| Componente | Detalle |
|---|---|
| Host | Ubuntu Server 22.04 (jammy), Docker + Compose |
| OCS (web) | `http://192.168.1.250:8081/ocsreports/` |
| OCS (API JSON) | `http://192.168.1.250:8081/ocsapi/v1` (usuario `sistemas`, perfil `sadmin`) |
| OCS (receptor de inventario) | `http://192.168.1.250:8081/ocsinventory` ← **raíz, no bajo `/ocsreports`** |
| Imagen Docker | `ocsinventory/ocsinventory-docker-image:2.12.1` (base Ubuntu 22.04) |
| Contenedores | `ocsinventory-server` (Apache 2.4.52 + mod_perl2 + PHP), `ocsinventory-db` (MariaDB), `ocsinventory-proxy` (nginx, **detenido**) |
| BD OCS | base `ocsweb`, usuario `<OCS_DB_USER>`; tablas por sección: `hardware`, `bios`, `networks`, `software`, … **no existen** `ocs_computers` ni `hosts` |
| SysAdmin (Yule) | `https://192.168.1.250:6060/yule/`, contenedores `sysadmin_db` / `sysadmin_django` / `sysadmin_nginx` |
| Conflicto de puertos | Puertos 80/443 del host ocupados por Hikvision → OCS quedó en `:8081` y su proxy nginx se detuvo |

---

## 3. Síntomas reportados (adjuntos)

**Captura 1 — Panel web de OCS (`/ocsreports/`, sección Equipos OCS):**

```
Total: 0 equipos detectados
Hostname | Tipo | MAC/Serial | IP | Usuario | Estado | Último reporte
(No hay equipos que coincidan con los filtros)
Maquina(s) 0 · Windows 0 · Unix 0 · Android 0 · Otros 0
Sistema Operativo 0 · Software 0
Equipos que contactaron hoy con el servidor: 0
```

**Captura 2 — Panel de Yule (SysAdmin `/yule/`):** estado *Conectado*,
sincronizaciones *Exitosa*, pero contadores de equipos en 0.

**Interpretación:** el panel de OCS confirma que **ningún agente ha reportado
nunca**. No es un problema de sincronización de Yule: es que la fuente de datos
está vacía.

---

## 4. Cronología de hallazgos

| # | Hallazgo | Impacto |
|---|---|---|
| 1 | `Alias /ocsreports` apunta al docroot, pero **no existe** `ocsinventory/` ahí. El handler real está en `<Location /ocsinventory>` (línea 320 de `z-ocsinventory-server.conf`) | El agente debe apuntar a `http://server:8081/ocsinventory`, **no** a `/ocsreports` |
| 2 | `Cannot find XML::Entities` | `libxml-entities-perl` **no existe en Ubuntu 22.04** (no está en el índice de `apt`) |
| 3 | `Can't load SOAP::Transport::HTTP*` | `SOAP::Transport::HTTP2` es exigido por `Apache::Ocsinventory::SOAP` (rama mod_perl2) y **no lo trae ni la imagen ni `libsoap-lite-perl`** (el dist SOAP::Lite 1.27 no incluye `HTTP2.pm`) |
| 4 | XML de prueba mal formado → **400** | El handler exige `QUERY` y `DEVICEID` **en la raíz** del XML, y el `DEVICEID` con formato `NOMBRE-AAAA-MM-DD-HH-MM-SS` (`Apache::Ocsinventory::Server::System.pm:236`) |
| 5 | XML con formato válido → **500**, pero `hardware` crece 1 fila con **todos los campos `NULL`** | **Sin explicar.** Es el punto abierto más importante |
| 6 | `/ocsapi/v1/computers?limit=0` devuelve texto plano, no JSON | Bug en cliente Yule (corregido) |
| 7 | `/computers` con equipos devuelve un **dict indexado por ID** (`{"1": {...}}`), no una lista | Bug en cliente Yule (corregido): Yule contaba 0 equipos aunque OCS los tuviera |
| 8 | La imagen **no incluye el daemon `ocsagent`** | No hay inventario remoto disparado desde el servidor ni descarga de "bootstrap" |
| 9 | `error.log` es symlink a `/proc/self/fd/2` | Los errores se leen con `docker logs ocsinventory-server`, no con `tail` dentro del contenedor |

---

## 5. Estado actual: qué funciona y qué no

### Funciona (verificado)

- Web de OCS accesible y renderizando (con parche PHP 8 en `html_header.php`).
- API JSON de OCS responde 200 con autenticación.
- **Receptor Perl de inventario carga** (desapareció el mensaje "Web service will
  be unavailable") y **acepta un POST en `/ocsinventory`** (crea registro en
  `hardware`).
- Yule: detección *Conectado*, `sync_ocs --force` ejecuta sin error, **335/335
  tests OK**.
- Cambios persistidos en script idempotente: `patch_ocs_server.sh`.

### NO funciona / pendiente

*(Estado al 2026-09-25, ya superado — ver sección 0. Se conserva el histórico.)*

- ~~**Ningún equipo registrado en OCS** (`hardware` = 0 filas).~~ Resuelto: 1 equipo real.
- ~~**Error 500** al digerir un inventario, con fila creada a medias.~~ Era el XML de prueba incompleto.
- ~~Agente Windows **no verificado** de punta a punta.~~ Verificado: `POST 200`, inventario en Yule.
- ~~La primera verificación end-to-end **nunca se completó**.~~ Completada.

Pendientes reales: ver 0.4.

> **Addendum 2026-09-29.** Lo que este informe dejó pendiente —"el software se
> consulta a OCS cada vez que alguien abre la página y no queda guardado"— se
> cerró al día siguiente con `inventario.SoftwareInstalado`, las dos vistas de
> software y el cron diario a las 03:07. El equipo de prueba `W11F35F` quedó
> vinculado al activo 24 y es el único con software guardado: de 24 activos,
> 23 siguen sin `equipo_ocs`. Ver `FASES.md` (FASE 7B-bis).

---

## 6. Cambios aplicados (para revisión del arquitecto)

### 6.1 En el contenedor OCS (efímeros — se pierden con `--force-recreate`)

| Cambio | Motivo |
|---|---|
| `cpanm XML::Entities` (Perl puro, sin dependencias) | Falta `XML::Entities`; el paquete de distro no existe en jammy |
| Archivo creado `/usr/local/share/perl/5.34.0/SOAP/Transport/HTTP2.pm` con `SOAP::Transport::HTTP2::Apache` heredando de `SOAP::Transport::HTTP::Apache` | La rama mod_perl2 de OCS lo exige y nadie lo provee. Alternativa preferible: **instalar una imagen oficial sobre Debian**, que ya incluye el stack |
| Copia parcheada de `html_header.php` (bug PHP 8 que dejaba la consola en blanco) | Render de la web |
| `OCS_OPT_LOGLEVEL` subido de `0` a `512` (en la config de Apache del contenedor) | Diagnóstico. **Dejar en 0 en producción** |

Los 3 primeros están automatizados en `patch_ocs_server.sh` (idempotente) y en el
repositorio del proyecto.

### 6.2 En SysAdmin (persistentes, en el repo)

| Archivo | Cambio |
|---|---|
| `backend/yule/client.py` | `computers_limit=1000` (OCS 2.12 rechaza `limit=0`); helper `_json_body()` con error real de OCS; **`_computers_from_payload()`** que acepta lista, `{"computers": [.]}` y **dict indexado por ID**; inyecta `id` desde la clave del dict; **`_find_software_rows()`** que localiza la sección de software bajo la clave `""` |
| `backend/yule/sync.py` | `_get_ci()` sin distinguir mayúsculas; `_section()` acepta dict o lista; `_lista()` para secciones 1-a-N; `_red_principal()` empareja `hardware.IPADDR` con la interfaz física; `_procesador()` usa `PROCESSORT`/`cpus`; `_almacenamiento_gb()` desde `storages.DISKSIZE`; `_parse_ocs_datetime()` interpreta `LASTCOME` como UTC; ID desde `accountinfo`/`hardware` |
| `backend/yule/tests.py` | 6 + 2 + 6 tests nuevos: `limit=0`, `null`, cuerpo vacío, texto no-JSON, dict indexado, software desde dict, payload real de OCS 2.12 completo, `LASTCOME` en UTC, MAC física frente a virtual |
| `OCS_INVENTORY_SETUP.md`, `AGENTS.md` | Documentación de todos los hallazgos |
| `patch_ocs_server.sh` | Reaplica los parches del contenedor |

---

## 7. Posibles causas a analizar (punto abierto)

> **Cerrado el 2026-09-28.** Ninguna de estas hipótesis era la causa: el
> receptor funcionaba y no recibía tráfico. La causa real fue la URL del agente
> (0.1) y los campos vacíos eran bugs del parser de Yule (0.3). Se conserva el
> análisis original.

## 7. Posibles causas a analizar (punto abierto)

> Estas son las hipótesis que requieren análisis. Ninguna está confirmada.

### 7.1 Del error 500 con fila `hardware` a medias (prioridad alta)

- **H1 — Desalineación de esquema.** La base se inicializó aplicando
  `./sql/ocsbase.sql` **a mano** (105 tablas) más el `ocsbase_new.sql` de la
  imagen. Si ese SQL no corresponde exactamente a la versión 2.12.1 de la
  imagen, algún `INSERT` de la ingesta puede fallar por columna inexistente o
  tipo incompatible. **Verificar**: comparar el esquema real de `hardware`,
  `bios`, `networks`, `software` con el DDL de la versión 2.12.1 oficial
  (`SHOW CREATE TABLE hardware\G`, y columnas de todas las tablas de sección).
- **H2 — Forma del payload.** `XML::Simple` convierte un elemento único en
  *hash* y los repetidos en *array*. El código Perl de OCS puede esperar siempre
  *array* en secciones como `HARDWARE`/`BIOS`/`NETWORKS`. El XML de prueba
  tenía una sola ocurrencia de cada una → la estructura no coincide con lo que
  espera el código → error a mitad de la ingesta. **Verificar**: comparar con un
  XML capturado de un agente real, o forzar `ForceArray` en
  `_get_xml_parser_opt`.
- **H3 — Sección obligatoria ausente.** Puede faltar una sección mínima que el
  agente real sí envía (p. ej. `WINDOWS`, `LOCAL_USERS`, `NETWORKS` con
  `SPEED`/`TYPE`, o `PROCESSORS` anidado) y cuya ausencia aborta el guardado.
- **H4 — Compresión.** El handler intenta `inflate` (zlib) y tiene fallback
  `OCS_OPT_COMPRESS_TRY_OTHERS`. Puede haber un camino de código que solo
  funciona con el payload comprimido que genera el agente oficial.
- **H14 — Módulo Perl `SOAP::Transport::HTTP2` fabricado a mano.** Hipótesis
  planteada por el arquitecto (módulo no provisto por la distro ni por la
  imagen). **Evidencia en contra**: la ingesta corre en el handler
  `Apache::Ocsinventory` (ruta `/ocsinventory`), que no carga
  `SOAP::Transport::HTTP2` en ningún momento; ese módulo solo lo requiere
  `Apache::Ocsinventory::SOAP`, que atiende `/ocsinterface` (web service SOAP
  legacy), ruta que no participa en la ingesta del inventario.
  **Test falsable en 1 minuto** (ver 8.3-bis): apartar el archivo y repetir el
  POST; si sigue devolviendo 500, la hipótesis queda descartada.

### 7.2 De que no entre ningún equipo (prioridad media)

- **H5 — El agente no está instalado o no reporta.** Es la causa más probable y
  a la vez la más trivial: no hay evidencia de que se haya instalado el agente
  en un cliente. Mientras no haya un agente, el resto no se puede medir.
- **H6 — URL del agente incorrecta.** Si se instaló con `/ocsreports` (que es
  la URL que aparece en la barra de direcciones del navegador), el agente hace
  POST a una ruta sin handler → 404 y no registra nada. Debe ser `/ocsinventory`.
- **H7 — Falta el daemon `ocsagent` en el servidor.** La imagen no lo incluye.
  Si el agente Windows, al instalar, intenta descargar un *bootstrap* o
  registrar un "contacto" previo y ese endpoint no existe, la instalación
  puede quedar incompleta sin mensaje claro.
- **H8 — Política del `ocsinventory-proxy` nginx (detenido).** El agente
  apuntaría directo al Apache del contenedor (puerto 8081). Si en producción se
  pretendiera enrutar por el proxy, habría que reconstruir esa ruta.
- **H9 — Versión del agente vs. servidor.** Se pretende instalar un agente
  Windows 2.11 sobre un servidor 2.12.1. Verificar la matriz de compatibilidad
  del protocolo de inventario.
- **H10 — Firewall / antivirus del cliente** bloqueando la salida del servicio
  del agente al puerto 8081.

### 7.3 De diseño (no bloqueante pero conviene resolver)

- **H11 — Falta `ServerName` en Apache** (warning constante en el arranque).
- **H12 — Distribución objetivo del contenedor.** La imagen oficial para
  Ubuntu 22.04 tiene un stack Perl incompleto (dos módulos faltantes). Evaluar
  migrar a la imagen basada en Debian, que es la usada por OCS como
  distribución soportada, para evitar el mantenimiento de parches propios.
- **H13 — `LOGLEVEL=512` activa escritura verbose de logs** en el contenedor.
  Volver a `0` tras el diagnóstico.

---

## 8. Evidencia y comandos de verificación

### 8.1 Estado del stack Perl dentro del contenedor

```bash
docker exec ocsinventory-server apache2ctl -S 2>&1 | grep -iE "unavailable|Entities"
# Estado actual: SIN salida (bien). Antes: "Can't load SOAP::Transport::HTTP*"
docker exec ocsinventory-server perl -e 'use XML::Entities; print "XML::Entities OK\n"'
docker exec ocsinventory-server perl -e 'require SOAP::Transport::HTTP2; print "HTTP2 OK\n"'
```

### 8.2 Comprobar recepción de inventario

```bash
# equipo real (debe dar filas; ahora da 0)
docker exec ocsinventory-db mysql -u<OCS_DB_USER> -p<OCS_DB_PASS> ocsweb \
  -e "SELECT ID,NAME,OSNAME,OSVERSION,LASTCOME FROM hardware ORDER BY ID DESC LIMIT 5;"

# conteo (indicador de "hay equipos")
docker exec ocsinventory-db mysql -u<OCS_DB_USER> -p<OCS_DB_PASS> ocsweb \
  -e "SELECT COUNT(*) AS equipos FROM hardware;"
```

### 8.3 Prueba de humo del receptor (XML sintético)

```bash
cat > /tmp/inv.xml <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<OCS>
  <QUERY>INVENTORY</QUERY>
  <CONTENT>
    <DEVICEID>PRUEBA-2026-09-25-14-30-00</DEVICEID>
    <HARDWARE><ID>1</ID><TYPE>1</TYPE><NAME>PRUEBA-PC</NAME>
      <OSNAME>Windows 11 Pro</OSNAME><MEMORY>16384</MEMORY></HARDWARE>
    <BIOS><SN>SN-PRUEBA-0001</SN><SSN>1</SSN></BIOS>
  </CONTENT>
</OCS>
XML
U=$(grep -E '^OCS_USER=' /opt/sysadmin/app/.env | cut -d= -f2)
P=$(grep -E '^OCS_TOKEN=' /opt/sysadmin/app/.env | cut -d= -f2)
curl -s -o /dev/null -w 'POST=%{http_code}\n' -X POST -u "$U:$P" \
  -H 'Content-Type: text/xml' --data-binary @/tmp/inv.xml \
  'http://192.168.1.250:8081/ocsinventory'
docker exec ocsinventory-db mysql -u<OCS_DB_USER> -p<OCS_DB_PASS> ocsweb \
  -e "SELECT ID,NAME,OSNAME,MEMORY FROM hardware;"
```

Resultado observado: `POST=500` y `hardware` con 1 fila cuyos campos están en
`NULL`. **Es el bug a investigar (ver 7.1).**

### 8.3-bis Test de descarte de H14 (el parche `SOAP::Transport::HTTP2`)

Objetivo: demostrar en un minuto si el módulo fabricado a mano participa en la
ingesta. Si el POST sigue fallando igual sin él, queda exonerado.

```bash
# 1) apartar el módulo (no borrar: se restaura en el paso 4)
docker exec ocsinventory-server mv \
  /usr/local/share/perl/5.34.0/SOAP/Transport/HTTP2.pm /tmp/HTTP2.pm.bak

# 2) repetir el POST del XML de prueba (mismo archivo /tmp/inv.xml)
U=$(grep -E '^OCS_USER=' /opt/sysadmin/app/.env | cut -d= -f2)
P=$(grep -E '^OCS_TOKEN=' /opt/sysadmin/app/.env | cut -d= -f2)
curl -s -o /dev/null -w 'POST_sin_HTTP2=%{http_code}\n' -X POST -u "$U:$P" \
  -H 'Content-Type: text/xml' --data-binary @/tmp/inv.xml \
  'http://192.168.1.250:8081/ocsinventory'

# 3) RESTAURAR inmediatamente (si no, el web service SOAP queda caído)
docker exec ocsinventory-server mv /tmp/HTTP2.pm.bak \
  /usr/local/share/perl/5.34.0/SOAP/Transport/HTTP2.pm
docker exec ocsinventory-server apache2ctl -k graceful
```

Criterio de decisión:

- `POST_sin_HTTP2=500` (igual que con el módulo) → **H14 descartada**: el parche no
  participa en la ingesta.
- `POST_sin_HTTP2=404` o 200 → **H14 confirmada**: el módulo fabricado altera el
  comportamiento del handler y hay que revisarlo (o adoptarlo tal cual de la
  distribución Debian).

### 8.4 Validación de la API y del pipeline Yule

```bash
curl -s -u "$U:$P" -H 'ocs-apirequest: true' -H 'Accept: application/json' \
  'http://192.168.1.250:8081/ocsapi/v1/computers?limit=5'
# sin equipos -> null ; con equipos -> {"1": {...}} (dict indexado por ID)

docker exec sysadmin_django python manage.py sync_ocs --force
docker exec sysadmin_django python manage.py shell -c \
 'from yule.client import build_client; c=build_client(); print(c.is_configured(), c.base_url, c.user, len(c.token), c.test_connection())'
```

### 8.5 Suite de pruebas (SysAdmin)

```bash
docker exec -e SECURE_SSL_REDIRECT=False -e DEBUG=True \
  sysadmin_django python manage.py test --noinput
# -> Ran 335 tests ... OK (44 de yule)
```

> Los overrides son obligatorios en el server: con `SECURE_SSL_REDIRECT=True`
> del `.env` el test client recibe 301 y falla masivamente (falso positivo).

### 8.6 Logs

```bash
docker logs --tail 80 ocsinventory-server 2>&1 | tail -40
docker exec ocsinventory-server sh -c 'grep -n "OCS_OPT_LOGLEVEL" /etc/apache2/conf-available/z-ocsinventory-server.conf'
```

---

## 9. Plan de acción propuesto

1. **Confirmar o descartar H5** (el más probable): instalar el agente Windows en
   un equipo de prueba con URL `http://192.168.1.250:8081/ocsinventory`,
   ejecutarlo manualmente y observar el POST en los logs. Si no hay POST, el
   problema es de cliente/red (H6, H7, H10). Si hay POST con 500, el problema es
   de ingesta (H1, H2, H3, H4).
2. **Capturar un XML real** que envíe el agente (el agente tiene modo verbose /
   log de detalle) y compararlo con el XML sintético para discriminar H2 vs H3.
3. **Validar el esquema** contra el DDL oficial de 2.12.1 (H1).
4. **Decisión de arquitectura**: permanecer en la imagen Ubuntu con parches
   propios o migrar a la imagen Debian (H12). La segunda opción elimina H1/H2 de
   raíz y reduce el mantenimiento a cero.
5. **Cierre**: con el primer equipo real en `hardware`, correr
   `sync_ocs --force`, verificar `/yule/equipos/`, devolver el `LOGLEVEL` a 0 y
   commitear los cambios de SysAdmin.

---

## 10. Riesgos y deuda técnica

- **Credenciales de OCS por defecto (confirmado).** La base de datos de OCS
  quedó con las credenciales **por defecto de la imagen oficial**, que están
  publicadas en el repositorio upstream de OCS. No es una clave elegida por
  nosotros, pero **es la clave real de producción**:
  1. **Rotarla** (cambiar la clave del usuario de BD de OCS y la variable de
     entorno del contenedor `ocsinventory-db`).
  2. El valor literal **no se escribe en ningún archivo del repositorio** (ni en
     este informe): los comandos usan los placeholders `<OCS_DB_USER>` y
     `<OCS_DB_PASS>`.
  3. El documento **sí contiene topología interna y rutas**, que no deberían
     salir de la organización: decidir antes de distribuirlo fuera del equipo.
- **Credenciales de SysAdmin**: la clave de base de datos de producción apareció
  en el historial de Git de una entrega anterior. Recomendado rotarla.
- Los parches del contenedor OCS son **efímeros**: un
  `docker compose up -d --force-recreate` los borra. Mitigado con
  `patch_ocs_server.sh`, pero es una condición de fragilidad.
- `OCS_OPT_LOGLEVEL=512` sigue activo en el contenedor actual (volver a 0 tras
  el primer inventario real, que es justo cuando sirve para diagnosticar).
- El `.env` de producción contiene `SECRET_KEY`, `PASSWORDS_ENCRYPTION_KEY` y el
  token de OCS: nunca debe versionarse. Recordar que `OCS_BASE_URL` **debe**
  terminar en `/ocsapi/v1`.

---

## 11. Anexos

- **Adjuntos sugeridos**: captura 1 (panel OCS en 0) y captura 2 (panel Yule en 0).
- **Archivos modificados en el proyecto**: `backend/yule/client.py`,
  `backend/yule/tests.py`, `OCS_INVENTORY_SETUP.md`, `AGENTS.md`,
  `patch_ocs_server.sh` (nuevo).
- **Documentación de referencia interna**: `OCS_INVENTORY_SETUP.md` (topología,
  trampas de la API, formato del XML, patching).
- **Script de parcheo**: `patch_ocs_server.sh` (idempotente; ejecutar tras cada
  recreación del contenedor OCS).
