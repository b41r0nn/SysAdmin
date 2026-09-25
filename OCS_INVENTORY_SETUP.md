# Instalación de OCS Inventory NG y conexión con Yule

> Estado real verificado el **2026-09-25** en `192.168.1.250`. Este documento
> refleja lo que quedó funcionando, no la guía ideal del fabricante.

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
docker exec ocsinventory-db mysql -uocsuser -pocspass ocsweb -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='ocsweb';"
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
docker exec ocsinventory-db mysql -uocsuser -pocspass ocsweb -e "
INSERT INTO operators (ID,FIRSTNAME,LASTNAME,PASSWD,ACCESSLVL,COMMENTS,NEW_ACCESSLVL,EMAIL,USER_GROUP,PASSWORD_VERSION)
VALUES ('Administrador','SysAdmin','Superusuario','$HASH',1,'Super usuario SysAdmin','sadmin','sistemas@redihos.local','sadmin',1)
ON DUPLICATE KEY UPDATE PASSWD=VALUES(PASSWD),NEW_ACCESSLVL='sadmin',USER_GROUP='sadmin',ACCESSLVL=1,PASSWORD_VERSION=1;"
```

Reglas que seonoraron en la práctica:

- `NEW_ACCESSLVL` debe ser `'sadmin'` (o el perfil que corresponda). NULL → error de permisos.
- `PASSWORD_VERSION=1`. Con `2` OCS fuerza cambio de clave al primer ingreso y el flujo se traba.
- El hash se genera con el **PHP del contenedor** (`password_hash`), no con `htpasswd` (eso es del proxy, que no se usa).

Usuarios que quedaron en producción: `admin`, `Administrador`, `yule` (todos `sadmin`).

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

Autenticación: HTTP **Basic** con el usuario OCS como user y la contraseña como
token, más el header `ocs-apirequest: true`.

## Configurar Yule en SysAdmin

En `https://192.168.1.250:6060/yule/configuracion/`:

- **URL**: `http://192.168.1.250:8081/ocsapi/v1` (termina en `/v1`, no en `/`)
- **Usuario**: `Administrador`
- **Token**: el mismo valor que `OCS_TOKEN` en el `.env` del server
- **Integración activa**: sí

Prioridad: `build_client()` (`backend/yule/client.py:241`) usa **primero** la
fila `ConfiguracionYule` activa en BD. `OCS_BASE_URL`/`OCS_USER`/`OCS_TOKEN` del
`.env` son solo fallback si no hay fila en BD.

## Agente en los equipos cliente

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
  -ArgumentList '/S','/SERVER=http://192.168.1.250:8081/ocsreports','/TAG=REDIHOS' -Wait
```

Verificar que reportó:

```bash
docker exec ocsinventory-db mysql -uocsuser -pocspass ocsweb -e "SELECT ID,NAME,LAST_POLL FROM hosts ORDER BY ID DESC LIMIT 5;"
```

## Limitación conocida: SOAP

```
ocsinventory-server: (SOAP): Cannot find XML::Entities
ocsinventory-server: Can't load SOAP::Transport::HTTP* - Web service will be unavailable
```

El paquete `libxml-entities-perl` **no existe** en Ubuntu 22.04 (jammy) y el
`apt-cache search entities` solo ofrece `node-entities`. Sin él, el **agente
SOAP no funciona**; la **API JSON/REST y la web sí**. No es bloqueante para
Yule. Se deja así a propósito.

## Comandos de uso diario

```bash
# estado
docker ps --filter name=ocsinventory --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'

# web
curl -s -o /dev/null -w 'WEB=%{http_code}\n' http://192.168.1.250:8081/ocsreports/

# ver usuarios y perfiles
docker exec ocsinventory-db mysql -uocsuser -pocspass ocsweb -e "SELECT ID,NEW_ACCESSLVL,USER_GROUP,ACCESSLVL,PASSWORD_VERSION FROM operators;"

# errores PHP recientes
docker logs --tail 40 ocsinventory-server 2>&1 | grep -iE "fatal|uncaught" | tail -5
```

## Troubleshooting

| Síntoma | Causa | Qué hacer |
|---|---|---|
| Solo el logo, página vacía | Parche `html_header.php` no aplicado o recreaste el contenedor | Reaplicar el parche de la sección de parche |
| "NO HAY DEFINIDO NINGÚN NIVEL DE PERMISOS" | `operators.NEW_ACCESSLVL` NULL | `UPDATE operators SET NEW_ACCESSLVL='sadmin' ...` |
| Login rechaza la clave correcta | `PASSWORD_VERSION=2` (fuerza cambio) | `UPDATE operators SET PASSWORD_VERSION=1;` |
| API devuelve 404 | Se consultó `/ocsapi/v1/` (no existe) | Consultar `/ocsapi/v1/computers?limit=1` |
| API devuelve 401/403 | Usuario/token mal, o falta header | Reusar `ocs-apirequest: true` + Basic auth |
| `/download/` da 403 | Requiere sesión de OCS | Enlace directo al archivo, o sesión iniciada |
| `ocsproxy` reinicia en loop | Choca con Hikvision en 80/443 | `docker compose stop ocsproxy` y usar `:8081` |
| Sin salida a GitHub | Proxy del server filtra sub-rutas | Descargar en Windows y `scp` |
| Sincronización Yule falla | URL mal configurada | Debe terminar en `/ocsapi/v1`; `build_client()` prioriza BD sobre `.env` |
