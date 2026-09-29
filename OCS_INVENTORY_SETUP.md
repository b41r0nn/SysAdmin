# Instalación de OCS Inventory NG y conexión con Yule

> Estado real verificado el **2026-09-25** en `192.168.1.250`. Este documento
> refleja lo que quedó funcionando, no la guía ideal del fabricante.

> **Antes de copiar cualquier bloque `mysql`:** definir las credenciales de la BD
> de OCS (vienen por defecto de la imagen oficial y hay que rotarlas):
> ```bash
> OCSUSER=<usuario de la BD ocsweb>
> OCSPASS=<clave de ese usuario>
> ```

## Qué es y cómo se relaciona con SysAdmin

OCS Inventory NG es software externo, independiente de SysAdmin. Escanea
la red y guarda su propio inventario en su propia base de datos. El
módulo Yule de SysAdmin NO habla con los equipos directamente — solo
consulta la API REST de OCS bajo demanda, cuando se aprieta
"Sincronizar ahora".

Dos relaciones distintas:

- **Agente instalado en cada equipo → Servidor OCS**: automática,
  constante, reporta sola cada cierto tiempo.
- **Servidor OCS → SysAdmin/Yule**: manual, bajo demanda, solo al
  sincronizar. Trae la lista de equipos y los compara por serial/MAC
  contra los `Activo` ya cargados en el inventario.
- **Coincide por serial/MAC** → aparece como candidato de vinculación,
  pero el enlace no se hace solo. Hay que entrar al admin de Django
  (`/admin/yule/equiposocs/`) y setear manualmente el campo
  `activo_local` en el registro correspondiente.
- **No coincide con nada** → queda "sin match", mismo criterio.

## Topología real (por qué es así)

| Servicio | Host:puerto | Notas |
|---|---|---|
| SysAdmin (Django+nginx) | `192.168.1.250:6060` (HTTPS) / `:6061` (HTTP→301) | Puerto 80 y 443 del host **ocupados por Hikvision** |
| OCS Inventory NG | `192.168.1.250:8081` (HTTP plano) | Puerto 8081 elegido para no chocar con Hikvision |

**El servicio `ocsproxy` (nginx de OCS) NO se usa**: levanta `80:80` y `443:443`
en el host, que colisionan con el frontend de Hikvision y lo dejan en
`Restarting (1)`. Además su upstream apunta a `ocsapplication`, que en esta
versión es alias de red del contenedor server. El proxy se queda detenido:

```bash
docker compose --project-directory ~/ocs/OCSInventory-Docker-Image/2.12.1 stop ocsproxy
```

El acceso directo al server OCS en `:8081` reemplaza al proxy sin perder nada
(necesario para la API, que el proxy además filtraba por htpasswd).

## Instalación (servidor 192.168.1.250)

1. Descargar la plantilla oficial:

   ```bash
   mkdir -p ~/ocs && cd ~/ocs
   git clone https://github.com/OCSInventory-NG/OCSInventory-Docker-Image.git
   cd OCSInventory-Docker-Image/2.12.1
   ```

2. Publicar el server en el host. En el servicio `ocsapplication`, reemplazar
   `expose: - "80"` por `ports: - "8081:80"`:

   ```bash
   python3 - <<'PY'
   import io
   p='docker-compose.yml'
   s=io.open(p,encoding='utf-8').read()
   old='    expose:\n      - "80"\n'
   new='    ports:\n      - "8081:80"\n'
   assert old in s, 'patron no encontrado'
   io.open(p,'w',encoding='utf-8').write(s.replace(old,new,1))
   print('OK: puerto 8081 agregado')
   PY
   ```

   > Editar el YAML con `sed` sobre varias líneas no funciona: `sed` no
   > matchea `\n` y el `&` de `&&` en el texto de reemplazo se interpreta
   > como "el texto que coincidió". Usar el bloque de Python de arriba.

3. Levantar solo db + server (el proxy se deja fuera):

   ```bash
   docker compose up -d ocsdb ocsapplication
   docker compose stop ocsproxy
   sleep 15
   curl -s -o /dev/null -w 'WEB=%{http_code}\n' http://192.168.1.250:8081/ocsreports/
   ```

   Esperado: `WEB=200`.

4. Firewall (solo si el puerto no responde desde otro PC):
   `sudo ufw allow 8081/tcp`

## Base de datos: lo que se inicializa y lo que NO

El `sql/ocsbase.sql` del repo se monta en `/docker-entrypoint-initdb.d/` y crea
el schema al primer arranque de MySQL. **No crea todas las tablas** y el
entrypoint borra `install.php`, así que el instalador web de OCS nunca corre.

Consecuencias reales (verificadas 2026-09-25):

- La tabla de usuarios se llama **`operators`** (NO `users`). Columnas útiles:
  `ID`, `PASSWD` (bcrypt `$2y$...`), `NEW_ACCESSLVL` (nivel de permisos),
  `USER_GROUP`, `ACCESSLVL`, `PASSWORD_VERSION`.
- `layouts` y `languages` quedan vacías. No es bloqueante: el layout por
  defecto del tema no las usa.
- El `admin` por defecto queda con `PASSWORD_VERSION=1` y
  `NEW_ACCESSLVL='sadmin'`.
- El error *"NO HAY DEFINIDO NINGÚN NIVEL DE PERMISOS PARA SU PERFIL"*
  (`backend/identity/methode/local.php:94`) aparece cuando
  `operators.NEW_ACCESSLVL` es NULL. La consulta que lo lee es:
  `SELECT new_accesslvl as accesslvl FROM operators WHERE id='<usuario>'`.

Contar tablas para saber si el schema está completo:

```bash
docker exec ocsinventory-db mysql -u"$OCSUSER" -p"$OCSPASS" ocsweb -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='ocsweb';"
# 105-109 = correcto
```

## Parche obligatorio: bug de PHP 8 en `html_header.php`

Sin este parche la consola OCS **muestra solo el logo** (página en blanco con
el header). Causa: bug de PHP 8 en el código de OCS 2.12.1 —
`html_header.php:236` llama `array_search()` sobre
`$_SESSION['OCS']['TRUE_PAGES']['ms_debug']` **sin** `is_array()`, mientras
que la línea 92 del mismo archivo sí lo valida. Se dispara cuando la sesión
entra con `mesmachines == "NOTAG"` (usuario sin etiqueta de máquina).

Síntoma en el log del contenedor:

```
PHP Fatal error: Uncaught TypeError: array_search(): Argument #2 ($haystack)
must be of type array, null given in
/usr/share/ocsinventory-reports/ocsreports/require/html_header.php:236
```

Aplicar (reemplaza la línea 236 por el `if` sin la cláusula `ms_debug`; el
cuerpo del bloque original que sigue queda intacto):

```bash
cat > /tmp/l236.txt <<'EOF'
if (isset($_SESSION["OCS"]["mesmachines"]) && $_SESSION["OCS"]["mesmachines"] == "NOTAG") {
EOF
docker cp /tmp/l236.txt ocsinventory-server:/tmp/l236.txt
docker exec -u root ocsinventory-server sh -c 'F=/usr/share/ocsinventory-reports/ocsreports/require/html_header.php; sed -i "236d" $F && sed -i "235r /tmp/l236.txt" $F && php -l $F'
docker restart ocsinventory-server
```

> `php -l` debe responder `No syntax errors detected`. Si la línea queda con
> `}` de más (error 500), es que se insertó un `if {...}` completo en vez del
> `if {` de apertura: el cuerpo del bloque original ocupa las líneas siguientes.

Como el archivo vive en la imagen (no en volumen), el parche se pierde si se
recrea el contenedor. Respaldo:

```bash
mkdir -p ~/ocs/OCSInventory-Docker-Image/2.12.1/patches
docker cp ocsinventory-server:/usr/share/ocsinventory-reports/ocsreports/require/html_header.php \
  ~/ocs/OCSInventory-Docker-Image/2.12.1/patches/
```

## Usuarios y credenciales

Crear un usuario de API dedicado (NO usar `admin`):

```bash
HASH=$(docker exec ocsinventory-server php -r 'echo password_hash("CLAVE_OCS_AQUI", PASSWORD_BCRYPT);')
docker exec ocsinventory-db mysql -u"$OCSUSER" -p"$OCSPASS" ocsweb -e "
INSERT INTO operators (ID,FIRSTNAME,LASTNAME,PASSWD,ACCESSLVL,COMMENTS,NEW_ACCESSLVL,EMAIL,USER_GROUP,PASSWORD_VERSION)
VALUES ('Administrador','SysAdmin','Superusuario','$HASH',1,'Super usuario SysAdmin','sadmin','sistemas@redihos.local','sadmin',1)
ON DUPLICATE KEY UPDATE PASSWD=VALUES(PASSWD),NEW_ACCESSLVL='sadmin',USER_GROUP='sadmin',ACCESSLVL=1,PASSWORD_VERSION=1;"
```

Reglas que seonoraron en la práctica:

- `NEW_ACCESSLVL` debe ser `'sadmin'` (o el perfil que corresponda). NULL → error de permisos.
- `PASSWORD_VERSION=1`. Con `2` OCS fuerza cambio de clave al primer ingreso y el flujo se traba.
- El hash se genera con el **PHP del contenedor** (`password_hash`), no con `htpasswd` (eso es del proxy, que no se usa).

Usuarios que quedaron en producción: `admin`, `Administrador`, `yule`,
`sistemas` (todos `sadmin`). El que usa Yule es **`sistemas`**; su contraseña
vive cifrada (Fernet) en `yule_configuracionyule.password_cifrada` y también en
`OCS_TOKEN` del `.env` como fallback. No está en este repo.

> Ojo con el hash: los bcrypt contienen `$`, así que **nunca** pongas `$HASH`
> dentro de un `-e "..."` de mysql entre comillas dobles (bash expande `$2y$...`
> y el hash queda corrupto). Usa un heredoc sin comillas, que hace una sola
> expansión:
> ```bash
> HASH=$(docker exec -e C="$CLAVE" ocsinventory-server php -r 'echo password_hash(getenv("C"), PASSWORD_BCRYPT);')
> cat > /tmp/set_ops.sql <<SQL
> INSERT INTO operators (ID,FIRSTNAME,LASTNAME,PASSWD,ACCESSLVL,COMMENTS,NEW_ACCESSLVL,EMAIL,USER_GROUP,PASSWORD_VERSION)
> VALUES ('sistemas','SysAdmin','Sistemas','${HASH}',1,'Usuario API para Yule','sadmin','sistemas@redihos.local','sadmin',1)
> ON DUPLICATE KEY UPDATE PASSWD=VALUES(PASSWD),NEW_ACCESSLVL='sadmin',USER_GROUP='sadmin',ACCESSLVL=1,PASSWORD_VERSION=1;
> SQL
> docker exec -i ocsinventory-db mysql -u"$OCSUSER" -p"$OCSPASS" ocsweb < /tmp/set_ops.sql
> rm -f /tmp/set_ops.sql
> ```

## Validar la API

El endpoint raíz `/ocsapi/v1/` responde **404** y eso es normal: no está
definido. Los endpoints que usa Yule sí existen (`computers`, `computer/{id}`,
ver `backend/yule/client.py:172,202`):

```bash
curl -s -o /dev/null -w 'api=%{http_code}\n' -u '<OCS_USER>:<OCS_TOKEN>' \
  -H 'ocs-apirequest: true' -H 'Accept: application/json' \
  'http://192.168.1.250:8081/ocsapi/v1/computers?limit=1'
```

`200` = autenticación OK. `null` en el cuerpo = todavía no hay equipos
inventariados, no es un error.

**No existe una tabla `ocs_computers`** en esta versión (ni `hosts`). El
inventario vive en las tablas por sección: `hardware`, `bios`, `networks`,
`software`, `memories`, `storages`, `monitors`, `usbdevices`, `registry`, etc.
El indicador de "hay equipos" es el conteo de `hardware` (una fila por máquina
inventariada):

```bash
docker exec ocsinventory-db mysql -u"$OCSUSER" -p"$OCSPASS" ocsweb -e "SELECT COUNT(*) AS equipos FROM hardware;"
```

### Trampa: `/computers` NO acepta `limit=0`

| Petición | Respuesta |
|---|---|
| `?limit=0` | texto plano que empieza con `Argu...` (error de argumento) |
| sin `limit` | igual: texto plano |
| `?limit=1` / `5` / `100` | JSON (`null` si no hay equipos) |

OCS 2.12 rechaza `limit=0`, así que **`get_computers()` no puede pedir "todos"
con `limit=0`** (que era lo que hacía la app antes del fix del 2026-09-25:
`response.json()` moría con *"Expecting value: line 1 column 1 (char 0)"* y el
sync quedaba en *fallo*). Ahora el cliente pide `limit=1000`
(`OCSClient.computers_limit`) y, si OCS contesta texto plano, el error que se
reporta incluye el mensaje real de OCS en vez de un error de parseo de JSON.

Autenticación: HTTP **Basic** con el usuario OCS como user y la contraseña como
token, más el header `ocs-apirequest: true`.

### Trampa: `/computers` devuelve un dict indexado por ID, no una lista

Con equipos inventariados, OCS 2.12 responde:

```json
{ "1": { "hardware": { "ID": 1, "NAME": "PC-01", "DEVICEID": "PC-01-2026-09-25-14-30-00" },
         "bios": [], "software": [], "networks": [] } }
```

Es un **dict keyed por ID**, no `[...]`. `get_computers()` solo miraba
`{"computers": [...]}` o una lista, así que contaba **0 equipos aunque OCS
devolviera el equipo** (log: `Unexpected OCS response format`). Corregido el
2026-09-25 con `OCSClient._computers_from_payload()`, que acepta las tres
formas; `get_software()` también acepta el dict indexado para
`computer/{id}`. Cubierto por `test_dict_indexado_por_id_se_parsea` y
`test_software_desde_dict_indexado_por_id` en `backend/yule/tests.py`.

La clave de cada equipo (el `ID` de `hardware`) es el `computer_id` que se pasa
a `computer/{id}` para traer el software.

### Trampa: cada sección llega con la forma de su tabla

Además del dict indexado por ID, **cada sección tiene una forma distinta según la
tabla de la que viene**. Los nombres de columna son los de la BD, en
**mayúsculas**. Con un equipo real inventariado:

| Dato | Dónde está realmente | Trampa |
|---|---|---|
| Serial del sistema | `bios[0].SSN` | `bios` es una **lista**, no un dict, y la clave es `SSN`, no `SN` |
| Nombre del CPU | `hardware.PROCESSORT` | `hardware.PROCESSORS` es la **frecuencia en MHz** (entero `1300`), no el nombre |
| IP del equipo | `hardware.IPADDR` | `networks` trae 48 interfaces en un portátil; la 1.ª es virtual y sin IP |
| MAC del equipo | `networks[].MACADDR` **de la interfaz que tiene esa IP** | la 1.ª es la virtual del firewall (`00:09:0F:...`), inservible para cruzar contra el inventario local |
| Usuario | `hardware.USERID` + `hardware.WORKGROUP` | **no hay clave `user` en la raíz**; la UI lo muestra como `dominio\usuario` |
| Disco total | `storages[].DISKSIZE` | viene en **MB**, hay que dividir entre 1024 |
| Último reporte | `hardware.LASTCOME` | es **UTC** (lo evalúa `NOW()` de la BD) y llega sin zona horaria |
| Software | `computer/{id}` → clave **literal vacía `""`** | buscar la clave `"software"` devuelve lista vacía siempre |

La razón de fondo: el JSON es una volcado directo de las tablas, sin un esquema
único. Por eso `backend/yule/sync.py` tiene `_get_ci()` (no distingue
mayúsculas), `_section()` (normaliza dict y lista) y `_lista()` (secciones 1-a-N).

Verificado contra un agente real (Dell Latitude 3450, Windows 11 Pro 24H2):

```bash
docker exec sysadmin_db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -x -c "SELECT id_ocs,nombre_host,usuario_dominio,serial_bios,mac_address,ip_address,procesador,almacenamiento_total_gb,ultimo_reporte_ocs FROM yule_equipoocs;"'
```

## Configurar Yule en SysAdmin

En `https://192.168.1.250:6060/yule/configuracion/`:

- **URL**: `http://192.168.1.250:8081/ocsapi/v1` (termina en `/v1`, no en `/`,
  y tampoco es `/ocsreports` que es la web)
- **Usuario**: `sistemas`
- **Contraseña**: la del usuario OCS `sistemas` (se guarda cifrada con Fernet)
- **Integración activa**: sí

Prioridad: `build_client()` (`backend/yule/client.py:241`) usa **primero** la
fila `ConfiguracionYule` activa en BD. `OCS_BASE_URL`/`OCS_USER`/`OCS_TOKEN` del
`.env` son solo fallback si no hay fila en BD.

### Si Yule queda en "Parcial" y no trae nada

"Parcial" en el historial **no** significa sincronización parcial: significa que
el sync ni siquiera se ejecutó. Casi siempre es `is_configured()` en falso
(`client.py:41` exige URL + usuario + token), y el mensaje en
`yule_sincronizacionlog.mensaje_error` lo dice literal:
"Integración OCS desactivada o sin configurar. No se sincronizó."

Diagnóstico (siempre por `sysadmin.settings.base`: el paquete
`sysadmin.settings` está vacío y con él Django responde "The SECRET_KEY setting
must not be empty"):

```bash
docker exec sysadmin_db psql -U sysadmin_user -d sysadmin_db -x -c "SELECT id, activa, integracion_activa, url, usuario, (password_cifrada <> '') AS tiene_password FROM yule_configuracionyule;"
docker exec sysadmin_db psql -U sysadmin_user -d sysadmin_db -c "SELECT fecha_inicio, estado, coalesce(mensaje_error,'') AS mensaje FROM yule_sincronizacionlog ORDER BY id DESC LIMIT 5;"
docker exec sysadmin_django python manage.py shell -c 'from yule.client import build_client; c = build_client(); print("configurado:", c.is_configured(), "| url:", c.base_url, "| user:", c.user, "| token_len:", len(c.token), "| test:", c.test_connection())'
```

Causas, en orden de frecuencia:

1. **Contraseña vacía** → `token: ''` → `is_configured()` falso. Es el caso más
   común: se llena la URL y el usuario pero no la contraseña.
2. **URL sin `/v1`** (o apuntando a `/ocsreports`) → 404 → error de cliente.
3. **`integracion_activa` desmarcado** → `build_client()` devuelve un cliente
   vacío a propósito (`client.py:255`).
4. **`PASSWORDS_ENCRYPTION_KEY` inválida en el `.env`** → `build_fernet()` lanza
   `ValueError: Fernet key must be 32 url-safe base64-encoded bytes` y **la
   contraseña nunca se puede guardar** (ni desde el formulario, que revienta en
   el `save()`). Debe ser una clave Fernet válida de 44 caracteres.

Si la clave Fernet estaba mal, la 1 credencial del vault de passwords que
venía del dump local queda ilegible (no se puede recuperar: estaba cifrada con
la clave del entorno de desarrollo). Hay que volver a capturarla.

## Agente en los equipos cliente

> El procedimiento completo (instalación gráfica y silenciosa, despliegue por GPO,
> verificación, `ocsinventory.ini`, errores frecuentes y desinstalación) está en
> **`MANUAL_AGENTE_OCS.md`**, que es el documento que se entrega a Sistemas.

### La URL del agente: `/ocsinventory` y nada más

**Este fue el bug que costó el diagnóstico entero.** OCS tiene tres rutas y no son
interchangeables:

| Ruta | Para qué | Dónde se configura |
|---|---|---|
| `/ocsinventory` | **receptor** de inventarios | **el agente** |
| `/ocsapi/v1` | API JSON | Yule (`/yule/configuracion/`) |
| `/ocsreports/` | panel web | el navegador |

Si el agente apunta a `/ocsreports` o a `/ocsapi/v1` no hay error visible: el
servidor responde y simplemente **nunca llega un inventario**. El panel muestra
`Total: 0 equipos detectados` y parece un fallo del servidor.

Durante la instalación, en el campo del servidor escribir exactamente:

```
http://192.168.1.250:8081/ocsinventory
```

Sin barra final, sin subruta. Para cambiarlo en un equipo ya instalado (PowerShell
como administrador):

```powershell
& "C:\Program Files\OCS Inventory Service\OcsInventoryService.exe" /ocsinventory
```

Comprobar que el agente corrió de verdad (access log del server):

```bash
docker logs --tail 40 ocsinventory-server 2>&1 | grep "POST /ocsinventory"
```

Debe aparecer una línea `POST /ocsinventory` con la IP del cliente y el
`User-Agent` del agente. Si no aparece, el agente no está reportando por mucho que
el servicio esté "en ejecución".

**El repo del agente es `WindowsAgent`, no `OCSInventory-Agent`** (este último
da 404):

- Releases: https://github.com/OCSInventory-NG/WindowsAgent/releases
  (asset `OCS-Windows-Agent-2.11.0.1_x64.zip`)
- Página oficial: https://ocsinventory-ng.org → *Downloads*

### Servidor sin salida a internet

El server tiene **GitHub filtrado por proxy**: `https://github.com` responde
`200` pero cualquier sub-ruta (`/repos/...`, `objects.githubusercontent.com`,
`api.github.com`) responde `404`. Por eso hay que descargar en Windows y
copiar:

```powershell
$z = Get-ChildItem "$env:USERPROFILE\Downloads" -Filter "*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$d = "$env:USERPROFILE\Downloads\ocs_agent"
Expand-Archive -Path $z.FullName -DestinationPath $d -Force
$e = Get-ChildItem $d -Recurse -Filter "*.exe" | Select-Object -First 1
scp $e.FullName sistemas@192.168.1.250:/tmp/OcsInventoryAgent.exe
```

```bash
docker cp /tmp/OcsInventoryAgent.exe ocsinventory-server:/var/lib/ocsinventory-reports/download/
docker exec -u root ocsinventory-server chown www-data:www-data \
  /var/lib/ocsinventory-reports/download/OcsInventoryAgent.exe
curl -s -o /dev/null -w 'descarga=%{http_code}\n' \
  'http://192.168.1.250:8081/download/OcsInventoryAgent.exe'
```

El directorio `/download/` **nace vacío** (no hay `index.php` → 404). OCS no
precarga agentes; el `403 Forbidden` en `/download/` sin sesión es normal, pero
un archivo suelto dentro sí se descarga por URL directa.

URL final de descarga: `http://192.168.1.250:8081/download/OcsInventoryAgent.exe`

### Instalación silenciosa en el cliente

```powershell
Start-Process "$env:USERPROFILE\Downloads\ocs_agent\OCS-Windows-Agent-2.11.0.1_x64\OCS-Windows-Agent-Setup-x64.exe" `
  -ArgumentList '/S','/SERVER=http://192.168.1.250:8081/ocsinventory','/TAG=REDIHOS' -Wait
```

> **La URL del agente es `http://192.168.1.250:8081/ocsinventory`**, NO
> `/ocsreports`. `/ocsreports` es la aplicación web; el handler Perl que recibe
> el XML del inventario está en la raíz (`<Location /ocsinventory>` en
> `/etc/apache2/conf-available/z-ocsinventory-server.conf`). Con `/ocsreports`
> el agente no registra nada.

Verificar que reportó (no existe tabla `hosts`; el inventario vive en `hardware`):

```bash
docker exec ocsinventory-db mysql -u"$OCSUSER" -p"$OCSPASS" ocsweb -e "SELECT ID,NAME,OSNAME,LASTCOME FROM hardware ORDER BY ID DESC LIMIT 5;"
```

## El receptor de inventarios: `/ocsinventory` (no `/ocsreports`)

Este es el punto que más cuesta: **la web de OCS puede verse perfecta y aun así
no registrar ningún equipo**, porque el receptor es otro modulo Perl.

| Ruta | Qué es | Quién la usa |
|---|---|---|
| `/ocsreports/` | aplicación web (PHP) | el operador en el navegador |
| `/ocsapi/v1/...` | API JSON | Yule (`backend/yule/client.py`) |
| `/ocsinventory` | **handler Perl que ingiere el XML del agente** | el agente en cada cliente |
| `/download/*.exe` | descarga de agentes | el operador |
| `/ocsinterface` | web service SOAP legacy | nadie (ver más abajo) |

El agente manda XML (opcionalmente comprimido con zlib) y OCS lo guarda por
secciones en `hardware`, `bios`, `networks`, `software`, etc.

### Por qué el receptor nace roto en esta imagen

La imagen `ocsinventory/ocsinventory-docker-image:2.12.1` (Ubuntu 22.04) arranca
con el stack Perl incompleto. Al hacer `apache2ctl -S` (o al mirar
`docker logs ocsinventory-server`):

```
ocsinventory-server: (SOAP): Cannot find XML::Entities
ocsinventory-server: Can't load SOAP::Transport::HTTP* - Web service will be unavailable
```

Son **dos** módulos faltantes, y cada uno tapa al anterior:

1. `XML::Entities` — el paquete `libxml-entities-perl` **no existe en jammy**
   (no está en el índice de `apt`). Se instala desde CPAN:
   `cpanm --notest XML::Entities` (Perl puro, sin dependencias).
2. `SOAP::Transport::HTTP2` — `Apache::Ocsinventory::SOAP` lo pide en la rama
   mod_perl2, pero ni la imagen ni `libsoap-lite-perl` lo traen (el dist de
   SOAP::Lite 1.27 **no** incluye `HTTP2.pm`). Se crea como alias de
   `SOAP::Transport::HTTP::Apache`, que ya trae la rama mod_perl2:
   ```perl
   package SOAP::Transport::HTTP2;
   use strict;
   require SOAP::Transport::HTTP;
   package SOAP::Transport::HTTP2::Apache;
   our @ISA = q(SOAP::Transport::HTTP::Apache);
   1;
   ```

Con ambos, el "Web service will be unavailable" desaparece y `/ocsinventory`
empieza a devolver 200 en vez de 404.

> Estos cambios viven **dentro del contenedor**: un
> `docker compose up -d --force-recreate` los borra. Para eso está
> `patch_ocs_server.sh` (idempotente) en la raíz del repo.

### Formato del XML (para probar el receptor a mano)

Dos requisitos que el handler valida y que no son obvios:

- `QUERY` y `DEVICEID` van **en la raíz** del XML, no dentro de `HEADER`:
  `<OCS><QUERY>INVENTORY</QUERY><CONTENT><DEVICEID>…</DEVICEID>…`.
- El `DEVICEID` **debe** cumplir `NOMBRE-AAAA-MM-DD-HH-MM-SS`
  (`Apache::Ocsinventory::Server::System.pm:236`,
  `$DeviceID =~ /^.+-\d{4}(?:-\d{2}){5}$/`). Con un id tipo `PRUEBA-001` el
  handler responde **400** y no registra nada.

Prueba rápida (el equipo insertado sirve para verificar el pipeline completo):

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
docker exec ocsinventory-db mysql -u"$OCSUSER" -p"$OCSPASS" ocsweb -e "SELECT ID,NAME FROM hardware;"
```

Limpiar después: `DELETE FROM hardware WHERE DEVICEID LIKE 'PRUEBA-%';`

## SOAP: limitation real (distinta al bug del receptor)

Arreglado `XML::Entities`, el web service SOAP de `/ocsinterface` carga, pero la
API SOAP de OCS NG 2.12 sigue sin ser usable de forma práctica (solo expone
operaciones de la base, no inventarios). Para Yule no hace falta: se usa la API
JSON de `/ocsapi/v1`. No usar SOAP.

## Comandos de uso diario

```bash
# estado
docker ps --filter name=ocsinventory --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'

# web
curl -s -o /dev/null -w 'WEB=%{http_code}\n' http://192.168.1.250:8081/ocsreports/

# ver usuarios y perfiles
docker exec ocsinventory-db mysql -u"$OCSUSER" -p"$OCSPASS" ocsweb -e "SELECT ID,NEW_ACCESSLVL,USER_GROUP,ACCESSLVL,PASSWORD_VERSION FROM operators;"

# errores PHP/Perl recientes
docker logs --tail 60 ocsinventory-server 2>&1 | grep -iE "fatal|uncaught|error|unavailable" | tail -10
```

> **Los logs de Apache/OCS se leen con `docker logs ocsinventory-server`, no
> con `tail` dentro del contenedor**: `/var/log/apache2/error.log` es un symlink
> a `/proc/self/fd/2`, o sea a la salida del proceso `docker exec` que lo lee
> (siempre vacío). Por eso el error "Web service will be unavailable" se ve al
> arrancar el contenedor o con `apache2ctl -S`, no en `error.log`.

## Lectura del software de los equipos (SysAdmin, 2026-09-29)

SysAdmin guarda lo que OCS reporta de cada equipo. Esto es distinto de leerlo
"a mano" desde la consola de OCS, y no reemplaza al agente: el agente es quien
reporta, SysAdmin solo guarda lo que llegó.

```bash
# Simular sin escribir nada
docker exec sysadmin_django python manage.py sincronizar_software --dry-run --verbose

# Sincronizar la flota (esto es lo que hace el cron a las 03:07)
docker exec sysadmin_django python manage.py sincronizar_software --verbose --pausa 2

# Un activo puntual
docker exec sysadmin_django python manage.py sincronizar_software --activo 24 --verbose

# Ver el log del cron
tail -f /var/log/sysadmin-software-sync.log
```

Páginas: `/inventario/<pk>/software/` (de un equipo) · `/inventario/software/`
(todos los equipos, con cuántos tienen cada programa).

Solo funciona en activos **vinculados** a un `EquipoOCS` (Yule › equipos sin
match). Hoy hay 24 activos y 1 vinculado.

**Diferencias con la consola de OCS que confunden:**

| | Consola de OCS | SysAdmin |
|---|---|---|
| Cada visita pega a OCS | no importa | no, lee la base |
| Registra bajas | no | sí, con fecha |
| Se actualiza solo | no | sí, a diario |
| Necesita el equipo encendido | sí (el agente acaba de reportar) | no, queda el último estado |

Que el equipo esté apagado **no** significa que el software esté en cero: queda
el último reporte que envió. Los cambios se detectan cuando el agente reporta
de nuevo, y el agente reporta cada hora.

Detalle de la lógica (qué se considera baja, por qué `"Unavailable"` no cuenta,
cómo se distingue un reemplazo de una versión en paralelo) en `FASES.md`,
sección FASE 7B-bis.

## Troubleshooting

| Síntoma | Causa | Qué hacer |
|---|---|---|
| Solo el logo, página vacía | Parche `html_header.php` no aplicado o recreaste el contenedor | `bash patch_ocs_server.sh` |
| **Ningún equipo aparece, ni en la web ni en `hardware`** | Receptor `/ocsinventory` roto (`XML::Entities` / `SOAP::Transport::HTTP2` faltantes) o agente apuntando a `/ocsreports` | `bash patch_ocs_server.sh` + URL del agente = `http://<server>:8081/ocsinventory` |
| `POST /ocsinventory` devuelve 404 | Web service Perl sin cargar | `bash patch_ocs_server.sh` + `apache2ctl -S` (el error sale por `docker logs`, no por `error.log`) |
| `POST /ocsinventory` devuelve 400 | `QUERY`/`DEVICEID` no están en la raíz, o el `DEVICEID` no cumple `NOMBRE-AAAA-MM-DD-HH-MM-SS` | Corregir el XML (ver "Formato del XML") |
| Yule marca *Conectado* pero 0 equipos | OCS no tiene equipos (nadie instaló el agente) **o** `/computers` devolvió dict por ID (bug ya corregido) | `SELECT COUNT(*) FROM hardware;` y revisar que el cliente esté actualizado |
| "NO HAY DEFINIDO NINGÚN NIVEL DE PERMISOS" | `operators.NEW_ACCESSLVL` NULL | `UPDATE operators SET NEW_ACCESSLVL='sadmin' ...` |
| Login rechaza la clave correcta | `PASSWORD_VERSION=2` (fuerza cambio) | `UPDATE operators SET PASSWORD_VERSION=1;` |
| API devuelve 404 | Se consultó `/ocsapi/v1/` (no existe) | Consultar `/ocsapi/v1/computers?limit=1` |
| API devuelve 401/403 | Usuario/token mal, o falta header | Reusar `ocs-apirequest: true` + Basic auth |
| `/computers` devuelve texto plano `Argu...` | Se pidió `limit=0` | Usar `limit` positivo (`client.computers_limit`) |
| `/download/` da 403 | Requiere sesión de OCS | Enlace directo al archivo, o sesión iniciada |
| `ocsproxy` reinicia en loop | Choca con Hikvision en 80/443 | `docker compose stop ocsproxy` y usar `:8081` |
| Sin salida a GitHub | Proxy del server filtra sub-rutas | Descargar en Windows y `scp` |
| Sincronización Yule falla | URL mal configurada | Debe terminar en `/ocsapi/v1`; `build_client()` prioriza BD sobre `.env` |
