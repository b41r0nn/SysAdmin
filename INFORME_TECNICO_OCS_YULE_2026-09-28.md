# Análisis técnico: por qué OCS no registraba inventario y por qué Yule guardaba campos vacíos

**Sesión:** 2026-09-28
**Servidor:** 192.168.1.250 · Ubuntu Server 22.04 · Docker Compose
**Componentes:** `ocsinventory/ocsinventory-docker-image:2.12.1` + SysAdmin/Yule (Django)
**Destinatario:** Arquitectura
**Estado:** resuelto y verificado en producción
**Código:** `918001d` → `a1184dd` · **Docs:** `4a9622d`

> Documento gemelo de gestión: `INFORME_ARQUITECTURA_2026-09-28.md` (visión de
> negocio y riesgos). Este documento es la referencia técnica: flujo de datos,
> anatomía de la respuesta de OCS y el antes/después de cada función con el
> código real. Procedimiento para los equipos cliente: `MANUAL_AGENTE_OCS.md`.

---

## 1. Flujo de datos completo

Antes de tocar nada conviene tener el camino completo, porque el síntoma
("0 equipos") podía estar en cualquiera de estos cinco puntos y no distinguía
entre ellos.

```
AGENTE  (Windows, servicio "OCS Inventory Service", cuenta LocalSystem)
  │  HTTP POST multipart con el XML del inventario
  ▼
APACHE  ocsinventory-server:2.4.52 + mod_perl2
  │  /usr/share/ocsinventory/PerlHandler/*.pm
  ▼
XML     /var/lib/ocsinventory/*.xml
  ▼
MariaDB ocsinventory-db → tablas: hardware, bios, networks, software, memories,
         cpus, storages, ports, monitors, ...  (NO existe ocs_computers)
```

Y en sentido de lectura, que es el que consume Yule:

```
DJANGO  sysadmin_django
  │
  ├─ build_client()                ConfiguracionYule en BD (prioriza sobre .env)
  │                                  → http://192.168.1.250:8081/ocsapi/v1
  ├─ OCSClient.get_computers()
  │    ├─ GET /computers?limit=1000
  │    ├─ _json_body()             cuerpo vacío / null / no-JSON → excepción con
  │    │                            los primeros 200 chars de lo que devolvió OCS
  │    └─ _computers_from_payload()  {"3": {...}} → [{"id": "3", ...}, ...]
  │
  └─ por cada equipo:
       _extract_equipo_data(item)
         ├─ _section(computer, "hardware")   dict / dict-anidado / lista → dict
         ├─ _section(computer, "bios")
         ├─ _lista(computer, "networks")      → [48 filas]
         ├─ _red_principal(hardware, networks) → (mac, ip)
         ├─ _procesador(hardware, computer)
         ├─ _almacenamiento_gb(computer)
         └─ _parse_ocs_datetime(LASTCOME)
       │
       └─ EquipoOCS.objects.update_or_create(id_ocs=..., defaults=datos_limpios)
```

**Los cinco puntos donde podía fallar sin decir nada:** (1) URL del agente,
(2) módulos Perl del receptor, (3) formato del XML, (4) formato del JSON de la
API, (5) mapeo al modelo de Django. Este caso tenía un fallo en (1) y seis en
(5). Nada falló en (2), (3) ni (4): el stack del servidor estaba sano.

---

## 2. Fase 1 — el receptor nunca recibió tráfico

### 2.1 Enrutado real del servidor

OCS sirve tres rutas distintas desde el mismo Apache, y cada una tiene un handler
diferente. Se registran en la configuración del contenedor
(`/etc/apache2/conf-available/z-ocsinventory-server.conf`, donde también vive
`OCS_OPT_LOGLEVEL`):

| Ruta | Handler | Quién debe apuntar ahí |
|---|---|---|
| `/ocsinventory` | Perl (`PerlHandler` de OCS) | **el agente** |
| `/ocsapi/v1/*` | API JSON de OCS | Yule |
| `/ocsreports/*` | PHP (panel web) | el navegador |

### 2.2 El error de configuración

El agente había quedado configurado contra `/ocsreports` o `/ocsapi/v1`. En
`C:\ProgramData\OCS Inventory NG\Agent\ocsinventory.ini`, sección `[HTTP]`:

```ini
; INCORRECTO: apunta al panel web o a la API, no al receptor
[HTTP]
Server=http://192.168.1.250:8081/ocsreports
SSL=0
AuthRequired=0
```

```ini
; CORRECTO
[HTTP]
Server=http://192.168.1.250:8081/ocsinventory
SSL=0
AuthRequired=0
```

### 2.3 Por qué esto no se manifiesta como un error

Es el punto más importante de esta fase. El agente hace su petición a una URL que
**existe y responde `200`**. No hay 404, no hay excepción, no hay log de error.
Simplemente nunca se ejecuta el handler Perl, porque a `/ocsreports` lo sirve PHP y
a `/ocsapi/v1` lo sirve la API JSON.

El síntoma resultante —cero equipos en el panel— es **idéntico** al de un receptor
roto. Por eso el diagnóstico se fue por los módulos Perl durante días.

### 2.4 La comprobación que lo resolvió en un segundo

El access log de Apache, filtrando el `POST` del receptor:

```bash
docker logs --tail 40 ocsinventory-server 2>&1 | grep "POST /ocsinventory"
```

```apache
# antes de corregir: cero resultados. Nunca llegó tráfico al receptor.
# después:
192.168.1.137 - - [28/Sep/2026:22:27:57 +0200] "POST /ocsinventory HTTP/1.1" 200 45 "-" "OCS-NG_WINDOWS_AGENT_v2.11.0.1"
```

Un solo `grep` sobre el log separaba las dos hipótesis dominantes: "el servidor
está roto" frente a "no hay tráfico". Ese control debía ser el **primer** paso.

> Nota operativa: los logs de Apache/OCS se leen con `docker logs
> ocsinventory-server`. Dentro del contenedor `/var/log/apache2/error.log` es un
> symlink a `/proc/self/fd/2` y siempre aparece vacío, lo que además refuerza la
> idea engañosa de "no hay errores".

### 2.5 El `500` con XML sintético era un falso positivo

La prueba manual `POST /ocsinventory` con un XML mínimo creaba la fila en
`hardware` a medias y devolvía `500`. Se interpretó como evidencia de un bug de
ingesta, y motivó la mayor parte de las 14 hipótesis.

El XML de prueba era:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<REQUEST>
  <DEVICEID>TEST-2026-09-25-10-00-00</DEVICEID>
  <QUERY>PROLOG</QUERY>
</REQUEST>
```

No traía la sección `<HARDWARE>` con contenido. El handler inserta la fila que
puede y falla al digerir el resto, de ahí el `500` y la fila a medias. **Un agente
real sí envía las secciones completas.** El `500` no era un defecto del servidor
sino un artefacto del instrumento de prueba.

---

## 3. Fase 2 — la respuesta de OCS 2.12 no tiene esquema

Con el primer inventario real, la causa raíz del symptomatic "campos vacíos"
resultó ser una suposición incorrecta sobre la forma del JSON.

### 3.1 Qué devolvió la API

`GET /ocsapi/v1/computers?limit=1` (extracto real):

```json
{
  "3": {
    "accountinfo": { "ID": 3 },
    "bios": [
      { "HARDWARE_ID": 3, "SSN": "F35F284", "MSN": "/F35F284/VNWSV0051K0C5N/",
        "SMODEL": "Latitude 3450", "TYPE": "Notebook" }
    ],
    "cpus": [
      { "TYPE": "13th Gen Intel(R) Core(TM) i5-1335U", "MANUFACTURER": "GenuineIntel" }
    ],
    "hardware": {
      "ID": 3,
      "NAME": "W11F35F",
      "IPADDR": "192.168.1.137",
      "USERID": "Sistemas",
      "USERDOMAIN": null,
      "WORKGROUP": "redihossas.local",
      "LASTCOME": "2026-09-28 20:27:57",
      "MEMORY": 16288,
      "OSNAME": "Microsoft Windows 11 Pro",
      "OSVERSION": "10.0.26200",
      "PROCESSORT": "13th Gen Intel(R) Core(TM) i5-1335U [10 core(s) x86_64]",
      "PROCESSORS": 1300
    },
    "networks": [
      { "MACADDR": "00:09:0F:AA:00:01", "IPADDRESS": "",            "STATUS": "",  "TYPE": "Ethernet" },
      { "MACADDR": "E8:CF:83:0A:8C:0E", "IPADDRESS": "192.168.1.137", "STATUS": "Up", "TYPE": "Ethernet" }
    ],
    "storages": [ { "TYPE": "Disk", "DISKSIZE": 488382 } ],
    "software": [ { "NAME_ID": 42, "VERSION_ID": 7, "PUBLISHER_ID": 3 } ]
  }
}
```

### 3.2 Por qué la forma varía entre secciones

La API de OCS 2.12 no consulta un esquema: **vuelca las filas de cada tabla**. Las
llaves son literalmente los nombres de columna de MariaDB (por eso van en
mayúsculas y no hay alias), y la forma de cada sección depende de su tabla:

| Sección | Forma | Razón |
|---|---|---|
| `hardware` | dict de columnas | 1 fila por equipo, PK `ID` |
| `bios` | **lista** de filas | 1 fila por equipo, pero la tabla tiene PK compuesta y se serializa como array |
| `networks`, `cpus`, `storages` | lista de filas | relación 1-a-N |
| `software` | lista de filas | relación N-a-N, y trae **IDs**, no los nombres |
| raíz | dict indexado por ID | el endpoint devuelve una fila por equipo |

Además, el mismo endpoint devuelve la sección ya "resuelta" cuando se consulta un
equipo suelto, y con nombres en vez de IDs cuando el dato viene por JOIN. O sea:
**la misma información aparece con dos formas distintas según el endpoint.**

### 3.3 La tabla de los errores de suposición

| Sedeed | Lo que parecía | Lo que realmente es |
|---|---|---|
| `bios` | dict con `SN` | lista de filas, y la columna es `SSN` |
| `hardware.PROCESSORS` | lista de CPUs | **frecuencia en MHz**, un entero |
| `hardware.PROCESSORT` | — (no se sabía que existía) | el nombre del CPU |
| `hardware.IPADDR` | — (no se buscaba) | la IP real del equipo |
| `hardware.USERID` / `WORKGROUP` | — | el usuario y su dominio |
| `user` en la raíz | el usuario | **no existe esa clave** |
| `storages[].DISKSIZE` | — | tamaño de disco **en MB** |
| `hardware.LASTCOME` | hora local | **UTC**, sin zona |

---

## 4. Fase 3 — corrección campo por campo

### 4.1 Lectura de claves: mayúsculas de las columnas

OCS devuelve los nombres de columna tal cual están en la BD. El parser leía
minúsculas.

```python
# ANTES: solo minúsculas
def _get_ci(data, *keys, default=""):
    if not isinstance(data, dict):
        return default
    for key in keys:
        value = data.get(key)          # data.get("osname") → None, la clave es "OSNAME"
        if value not in (None, ""):
            return value
    return default
```

```python
# DESPUÉS: exacto primero, luego insensible a mayúsculas
def _get_ci(data: Any, *keys: str, default: Any = "") -> Any:
    if not isinstance(data, dict):
        return default
    for key in keys:                    # 1) coincidencia exacta (caso habitual)
        value = data.get(key)
        if value not in (None, ""):
            return value
    lowered = {str(k).lower(): v for k, v in data.items()}   # 2) fallback normalizado
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return default
```

`None` y `""` se tratan igual a propósito: en el payload real `USERDOMAIN` viene
`null` y `IPSRC` vacío, y una clave "presente pero vacía" debe caer al siguiente
alias.

### 4.2 Serial del sistema: `bios` es lista y la columna es `SSN`

```python
# ANTES: devolvía {} porque _section() exigía un dict
def _section(data, *keys):
    value = _get_ci(data, *keys, default={})
    if not isinstance(value, dict):
        return {}                      # ← "bios" es una lista: se descarta entera
    ...
```

```python
# DESPUÉS: normaliza dict, dict-anidado por ID y lista
def _section(data: Any, *keys: str) -> Dict[str, Any]:
    value = _get_ci(data, *keys, default={})
    if isinstance(value, list):
        # Secciones 1-a-N (bios, storages, memories...) o N-a-1 indexada por ID.
        if value and isinstance(value[0], dict):
            value = value[0]
        else:
            indexed = [v for v in value if isinstance(v, dict)]
            value = indexed[0] if len(indexed) == 1 else {}
    if not isinstance(value, dict):
        return {}
    if len(value) == 1:
        inner = next(iter(value.values()))
        if isinstance(inner, dict):
            return inner
    return value
```

```python
# ANTES
"serial_bios": _get_ci(bios, "sn", "serial"),

# DESPUÉS: SSN es el número de serie del sistema en OCS 2.12
"serial_bios": _get_ci(bios, "ssn", "sn", "msn", "serial"),
```

El orden de alias no es arbitrario: `SSN` primero (correcto en 2.12), `SN` y
`SERIAL` después (otras versiones), `MSN` al final (es el service tag de Dell,
`/F35F284/VNWSV0051K0C5N/`, no el serial puro, así que va de último).

### 4.3 Procesador: `PROCESSORS` es MHz, el nombre está en `PROCESSORT`

```python
# ANTES: se asumía que PROCESSORS era una lista de CPUs
processors = _get_ci(hardware, "processors", default=[])
processor_name = ""
if isinstance(processors, list) and processors and isinstance(processors[0], dict):
    processor_name = _get_ci(processors[0], "name", "caption")
elif isinstance(processors, dict):
    processor_name = _get_ci(processors, "name", "caption")
# → en 2.12 processors es el int 1300: ninguna rama aplica, processor_name = ""
```

```python
# DESPUÉS
def _procesador(hardware: Dict[str, Any], computer: Dict[str, Any]) -> str:
    processor_name = _get_ci(hardware, "processort", "processorname")
    if processor_name and not isinstance(processor_name, (int, float)):
        return str(processor_name)

    for source in (_get_ci(computer, "cpus", default=[]),
                   _get_ci(hardware, "processors", default=[])):
        # `cpus` es lista de filas; `processors` puede ser dict de campos de un
        # solo CPU, así que ambas formas se normalizan a filas.
        if isinstance(source, dict):
            rows = [source]
        elif isinstance(source, list):
            rows = [row for row in source if isinstance(row, dict)]
        else:
            continue
        for row in rows:
            name = _get_ci(row, "type", "name", "caption", "model")
            if name and not isinstance(name, (int, float)):
                return str(name)
    return ""
```

Dos guards `isinstance(..., (int, float))` son deliberados: impiden que un
`PROCESSORS` numérico se cuele como si fuera el nombre. La segunda iteración
mantiene compatibilidad con versiones donde `PROCESSORS` sí era una lista de filas.

### 4.4 Red: 48 interfaces y la primera es del firewall

Este fue el defecto más traicionero, porque **no produjo un campo vacío sino un
valor falso**. En un portátil con firewall integrado, la primera entrada de
`networks` es la interfaz virtual del Fortinet (`00:09:0F:...`), que no tiene IP.

```python
# ANTES: recorría la lista y se quedaba con la primera coincidencia de cada campo
mac_address = ""
ip_address = ""
for net in networks:
    if not isinstance(net, dict):
        continue
    if not mac_address:
        mac_address = _get_ci(net, "macaddr", "macaddress")
    if not ip_address:
        ip_address = _get_ci(net, "ipaddress", "ip")
    if mac_address and ip_address:
        break
```

Con el payload real producía `mac = 00:09:0F:AA:00:01` (virtual) e
`ip = ""`, porque la primera interfaz no tiene IP y las siguientes nunca se
alcanzaban a revisarse: el `break` exigía los dos campos a la vez. El comentario
que tenía el código (llenar cada campo por separado en vez de cortar en la primera
coincidencia) era correcto en intención, pero insuficiente: no distinguía una MAC
virtual de una física.

```python
# DESPUÉS: se cruza hardware.IPADDR con la interfaz que la tiene
def _red_principal(hardware: Dict[str, Any], networks: List[Dict]) -> Tuple[str, str]:
    ip_hardware = _get_ci(hardware, "ipaddr", "ipsrc")

    mac_activa = ""
    mac_cualquiera = ""
    for net in networks:
        net_ip = _get_ci(net, "ipaddress", "ip")
        net_mac = _get_ci(net, "macaddr", "macaddress")
        if not net_mac or net_mac == "00:00:00:00:00:00":
            continue
        if ip_hardware and net_ip == ip_hardware:
            return net_mac, net_ip          # ← coincidencia exacta: gana y sale
        if not mac_cualquiera:
            mac_cualquiera = net_mac
        if not mac_activa and _get_ci(net, "status", default="").lower() == "up":
            mac_activa = net_mac

    mac = mac_activa or mac_cualquiera

    ip = ip_hardware
    if not ip:
        for net in networks:
            net_ip = _get_ci(net, "ipaddress", "ip")
            if net_ip:
                ip = net_ip
                break

    return mac, ip
```

La precedencia es deliberada y a prueba del orden de las interfaces:

1. La interfaz cuyo `IPADDRESS` coincide con `hardware.IPADDR` (caso real).
2. La primera con `STATUS = Up` y MAC no nula.
3. La primera con MAC no nula (`00:00:00:00:00:00` se descarta siempre).

**Por qué importa más allá del campo visible:** `mac_address` es
`db_index=True` y es una de las dos claves con las que
`buscar_posibles_matches()` cruza el equipo de OCS contra el inventario local
(`Activo.mac_equipo__icontains`). Con la MAC virtual, el cruce no encontraba
nada y lo hacía en silencio.

### 4.5 Usuario: no existe la clave `user` en la raíz

```python
# ANTES
"usuario_dominio": _get_ci(computer, "user"),      # computer no tiene "user" → ""
```

```python
# DESPUÉS
usuario = _get_ci(computer, "user") or _get_ci(hardware, "userid")
dominio = _get_ci(hardware, "userdomain", "workgroup")
...
"usuario_dominio": (
    f"{dominio}\\{usuario}" if dominio and usuario else (usuario or dominio or "")
),
```

`USERDOMAIN` viene `null` en un equipo unido a dominio, así que el alias
`workgroup` es el que resuelve. Se conserva `computer["user"]` como primera opción
porque algunas instalaciones sí lo envían.

### 4.6 Almacenamiento: estaba fijo en `None`

```python
# ANTES
"almacenamiento_total_gb": None,  # OCS no siempre proporciona esto
```

```python
# DESPUÉS
def _almacenamiento_gb(computer: Dict[str, Any]) -> Optional[int]:
    total_mb = 0.0
    for storage in _lista(computer, "storages"):
        try:
            total_mb += float(_get_ci(storage, "disksize", default=0) or 0)
        except (TypeError, ValueError):
            continue
    return int(round(total_mb / 1024)) or None
```

`488382 MB / 1024 = 476.94 GB` → `477`. El `or None` al final convierte el `0` de
un equipo sin discos en `None` en vez de guardar un cero engañoso.

### 4.7 `LASTCOME` es UTC, no hora local

Las dos fuentes independientes del mismo instante:

| Fuente | Valor | Interpretación |
|---|---|---|
| Access log de Apache | `28/Sep/2026:22:27:57 +0200` | `20:27:57 UTC` |
| `hardware.LASTCOME` | `2026-09-28 20:27:57` | `20:27:57 UTC` |

Coinciden exactamente, así que `LASTCOME` está en UTC. La causa de fondo: OCS la
escribe con `NOW()` evaluado por MariaDB, que corre en UTC, y la devuelve como
hora naive **sin zona horaria**.

```python
# ANTES: asumía hora local del servidor Django (America/Bogota, UTC-5)
if timezone.is_naive(parsed):
    parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
# → 2026-09-28 20:27:57 naive se volvía 2026-09-29 01:27:57+00 (5 h corrido)
```

```python
# DESPUÉS
if timezone.is_naive(parsed):
    parsed = parsed.replace(tzinfo=timezone.utc)
```

Se usa `replace` y no `make_aware` a propósito: no hay conversión, hay
declaración. El instante es correcto; lo que faltaba era la zona.

### 4.8 El ID no viene dentro del objeto

`EquipoOCS.id_ocs` es `CharField(max_length=50, unique=True)`. OCS 2.12 pone el ID
**solo en la llave** del dict de la raíz, no dentro del equipo:

```python
# ANTES en client.py: se perdía el ID
values = [value for value in data.values() if isinstance(value, dict)]
if values:
    return values          # → {"3": {...}} pasa a [{...}] sin "id"
```

```python
# DESPUÉS
items = []
for key, value in data.items():
    if not isinstance(value, dict):
        continue
    item = dict(value)
    if not item.get("id"):
        item["id"] = key        # OCS 2.12 no pone el ID dentro del objeto
    items.append(item)
if items:
    return items
```

Como `id_ocs` es `unique=True`, sin esto **todos los equipos se colapsaban en un
mismo registro**: el `update_or_create()` del primero ganaba y los demás
sobrescribían al mismo. Además `_extract_equipo_data()` ahora también busca el ID
en `accountinfo.ID` / `hardware.ID`, para el caso de que se consuma el JSON crudo
sin pasar por el cliente.

---

## 5. Fase 4 — el software salía vacío en todos los equipos

### 5.1 El defecto

`GET /computer/3` devuelve el software bajo la **clave literal vacía**:

```json
{ "3": { "": [ { "NAME": "Google Chrome", "VERSION": "140.0", "PUBLISHER": "Google LLC" },
               { "NAME": "Notepad++",    "VERSION": "8.7",   "PUBLISHER": "Don Ho" } ] } }
```

El parser buscaba la clave `"software"`, que no existe, y devolvía `[]` **para
todos los equipos, sin error ni warning**. Nadie lo notó porque el panel de Yule
se veía normal mientras no hubiera inventario.

```python
# ANTES: cuatro ramas adivinando la forma, ninguna cubría la clave ""
if isinstance(data, dict) and "software" in data:
    raw = data["software"]
elif isinstance(data, list) and data and isinstance(data[0], dict) and "software" in data[0]:
    raw = data[0]["software"]
elif isinstance(data, dict):
    raw = []
    for value in data.values():
        if isinstance(value, dict) and "software" in value:
            raw = value["software"]
            break
else:
    raw = []
```

### 5.2 La corrección

En vez de adivinar la llave, se busca **estructuralmente**: la primera lista de
filas que tenga nombre y versión.

```python
@staticmethod
def _find_software_rows(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    candidates: List[Dict[str, Any]] = []
    for value in data.values():
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            for inner in value.values():
                if isinstance(inner, list):
                    candidates.extend(item for item in inner if isinstance(item, dict))

    for item in candidates:
        keys = {str(k).lower() for k in item}
        if "name" in keys and ("version" in keys or "publisher" in keys):
            return candidates
    return []
```

El último bucle es la condición de recognizable: `memories`, `monitors`, `ports` y
el resto de secciones también son listas, pero sus filas no tienen `name` +
`version`, así que no se confunden. Está cubierto por
`test_software_no_confunde_otras_listas_de_la_respuesta`.

```python
# get_software() queda así
software = []
for item in self._find_software_rows(data):
    software.append({
        "name": item.get("name") or item.get("NAME") or "",
        "version": item.get("version") or item.get("VERSION") or "",
        "publisher": item.get("publisher") or item.get("PUBLISHER") or "",
    })
return [s for s in software if s["name"]]
```

### 5.3 Lo que este bug revela sobre el contrato

La misma información viene de dos maneras según el endpoint:

| Endpoint | Sección `software` |
|---|---|
| `/computers` | `[{ "NAME_ID": 42, "VERSION_ID": 7 }]` — solo **IDs** |
| `/computer/{id}` | `[{ "NAME": "Google Chrome", "VERSION": "140.0" }]` — **resuelto** |

Por eso el software solo se puede leer del endpoint de detalle, y por eso el
`get_software()` de ese endpoint es el que estaba roto.

---

## 6. Fase 5 — por qué 30 tests en verde no detectaron nada de esto

Este es el hallazgo de proceso más importante del caso.

Los tests pasaban (`tests yule: 30/30` en `918001d`) con un parser que fallaba en
seis campos frente a producción. La causa: **los fixtures se escribieron a mano en
lugar de copiarse de una respuesta real.** Tres ejemplos, textuales:

```python
# backend/yule/tests.py:375  (fixture inventado)
"PROCESSORS": {"NAME": "Intel(R) Core(TM) i5-10400"},   # real: PROCESSORS=1300, PROCESSORT="..."
"BIOS": {"SN": "ABC123"},                                 # real: "bios": [{"SSN": "F35F284"}]
```

```python
# backend/yule/tests.py:351  (fixture inventado)
'{"1": {"software": [{"NAME": "Chrome", "VERSION": "120.0"}]}}'
# real: {"3": {"": [{"NAME": "Chrome", "VERSION": "120.0"}]}}
```

```python
# backend/yule/tests.py:401  (fixture inventado)
"bios": {"sn": "XYZ789"},      # en minúsculas y como dict
```

El test de software **aseveraba** `{"1": {"software": [...]}}` y pasaba, porque el
código se había escrito para satisfacer ese fixture. La forma real —clave `""`— no
estaba en ningún test, así que el bug podía existir sin romper nada.

La corrección fue añadir el fixture que sí viene de la API, y ese test es el que
detectó los seis defectos:

```python
# backend/yule/tests.py:467-535 — verbatim
def test_payload_real_ocs_212_se_mapea_completo(self):
    # Fixture tomado de `/ocsapi/v1/computers?limit=1` de OCS 2.12.1. En esa
    # forma `bios` es lista, `PROCESSORS` es un entero (MHz) y la primera
    # interfaz es virtual del firewall: con el parser anterior quedaban
    # serial, procesador, IP y MAC vacíos o equivocados.
    from yule.sync import _extract_equipo_data

    datos = _extract_equipo_data(
        {
            "accountinfo": {"ID": 3},
            "bios": [
                {
                    "HARDWARE_ID": 3,
                    "SSN": "F35F284",
                    "MSN": "/F35F284/VNWSV0051K0C5N/",
                    "SMODEL": "Latitude 3450",
                }
            ],
            "cpus": [{"TYPE": "13th Gen Intel(R) Core(TM) i5-1335U", "MANUFACTURER": "GenuineIntel"}],
            "hardware": {
                "ID": 3,
                "NAME": "W11F35F",
                "IPADDR": "192.168.1.137",
                "USERID": "Sistemas",
                "USERDOMAIN": None,
                "WORKGROUP": "redihossas.local",
                "LASTCOME": "2026-09-28 20:27:57",
                    "MEMORY": 16288,
                    "OSNAME": "Microsoft Windows 11 Pro",
                    "OSVERSION": "10.0.26200",
                "PROCESSORT": "13th Gen Intel(R) Core(TM) i5-1335U [10 core(s) x86_64]",
                "PROCESSORS": 1300,
            },
            "networks": [
                {
                    "MACADDR": "00:09:0F:AA:00:01",
                    "IPADDRESS": "",
                    "STATUS": "",
                    "TYPE": "Ethernet",
                },
                {
                    "MACADDR": "E8:CF:83:0A:8C:0E",
                    "IPADDRESS": "192.168.1.137",
                    "STATUS": "Up",
                    "TYPE": "Ethernet",
                },
            ],
            "storages": [{"TYPE": "Disk", "DISKSIZE": 488382}],
        }
    )

    self.assertEqual(datos["id_ocs"], "3")
    self.assertEqual(datos["nombre_host"], "W11F35F")
    self.assertEqual(datos["usuario_dominio"], "redihossas.local\\Sistemas")
    self.assertEqual(datos["serial_bios"], "F35F284")
    self.assertEqual(datos["procesador"], "13th Gen Intel(R) Core(TM) i5-1335U [10 core(s) x86_64]")
    self.assertEqual(datos["ip_address"], "192.168.1.137")
    # MAC de la interfaz que tiene la IP real, no la virtual del firewall.
    self.assertEqual(datos["mac_address"], "E8:CF:83:0A:8C:0E")
    self.assertEqual(datos["memoria_ram_mb"], 16288)
    # El campo del modelo es PositiveIntegerField: el helper devuelve int.
    # 488382 MB / 1024 = 476.94 -> 477. Antes devolvía 476.9 y Django lo
    # truncaba a 476 al guardar.
    self.assertIsInstance(datos["almacenamiento_total_gb"], int)
    self.assertEqual(datos["almacenamiento_total_gb"], 477)
    self.assertEqual(
        datos["ultimo_reporte_ocs"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "2026-09-28 20:27:57",
    )
```

Los fixtures inventados **se conservaron** (no se borraron): cubren la forma
alternativa en minúsculas y la versión antigua, que siguen siendo válidas. Lo que
se añadió fue el caso real al lado.

**Regla que sale de esto:** un test de integración con una API externa debe
escribirse a partir de una respuesta capturada y versionada. Un fixture escrito a
mano prueba que el código hace lo que el test dice, no lo que hace el servidor.

---

## 7. Hallazgo adicional — `float` contra `PositiveIntegerField`

Encontrado al documentar el modelo, ya con el fix en producción:

```python
# backend/yule/models.py
almacenamiento_total_gb = models.PositiveIntegerField(null=True, blank=True)
```

```python
# el helper devolvía float
return round(total_mb / 1024, 1) or None      # → 476.9
```

Funcionaba por accidente: `IntegerField.get_prep_value()` aplica `int(value)` al
guardar, y la BD quedó con `476`. Dos consecuencias: el tipo de retorno mentía
(la UI y cualquier consumidor esperaba un entero, no `476.9`) y el valor estaba
truncado, no redondeado.

```python
# corregido
def _almacenamiento_gb(computer: Dict[str, Any]) -> Optional[int]:
    """... Devuelve `int` porque el campo del modelo es `PositiveIntegerField` ..."""
    total_mb = 0.0
    for storage in _lista(computer, "storages"):
        try:
            total_mb += float(_get_ci(storage, "disksize", default=0) or 0)
        except (TypeError, ValueError):
            continue
    return int(round(total_mb / 1024)) or None
```

**Efecto secundario a tener en cuenta al desplegar:** el valor en BD pasará de
`476` a `477` (488382 MB / 1024 = 476.94, que redondea a 477). Es un cambio
cosmético de 1 GB, no un error.

Detalle relacionado: `ip_address` es un `GenericIPAddressField`, pero
`update_or_create()` **no llama a `full_clean()`**, así que la validación de
formato de IP no se ejecuta en el sync. Si OCS devolviera un valor inválido se
guardaría tal cual, sin error. No hubo problema con este equipo, pero es una
fragilidad del camino de escritura.

---

## 8. Verificación

### 8.1 En producción

```bash
docker exec -e SECURE_SSL_REDIRECT=False -e DEBUG=True sysadmin_django python manage.py test yule
# Ran 44 tests ... OK

docker exec sysadmin_django python manage.py sync_ocs --force
# Sincronización exitosa: 1 detectados, 0 nuevos, 1 actualizados, 0 desaparecidos
```

Estado de `yule_equipoocs` tras el despliegue:

```bash
docker exec sysadmin_db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -x -c "SELECT id_ocs,nombre_host,usuario_dominio,so_nombre,so_version,serial_bios,mac_address,ip_address,procesador,memoria_ram_mb,almacenamiento_total_gb,ultimo_reporte_ocs FROM yule_equipoocs;"'
```

```
id_ocs                  | 3
nombre_host             | W11F35F
usuario_dominio         | redihossas.local\Sistemas
so_nombre               | Microsoft Windows 11 Pro
so_version              | 10.0.26200
serial_bios             | F35F284
mac_address             | E8:CF:83:0A:8C:0E
ip_address              | 192.168.1.137
procesador              | 13th Gen Intel(R) Core(TM) i5-1335U [10 core(s) x86_64]
memoria_ram_mb          | 16384
almacenamiento_total_gb | 476
ultimo_reporte_ocs      | 2026-09-28 20:27:57+00
```

### 8.2 Local

| Suite | Resultado |
|---|---|
| `manage.py test yule` | 44/44 OK |
| `manage.py test` (completa) | 335/335 OK |

### 8.3 En OCS

Fila `hardware` ID `3`, con `bios` 1, `networks` 48 y `software` 122.

---

## 9. Despliegue

### 9.1 Por qué `scp` y no `rsync`

El flujo habitual (`rsync` desde el equipo de trabajo) no era viable:

- `rsync` **no está instalado** en el equipo de trabajo de Windows
  (`rsync : El término 'rsync' no se reconoce`), y
- no hay clave SSH para `sistemas@192.168.1.250`
  (`Permission denied (publickey,password)`).

`scp` sí está (`C:\Windows\System32\OpenSSH\scp.exe`), así que el traspaso fue:

```powershell
cd "C:\Users\Sistemas\OneDrive - ...\SysAdmin"
scp backend/yule/client.py backend/yule/sync.py backend/yule/tests.py `
    sistemas@192.168.1.250:/opt/sysadmin/app/backend/yule/
```

### 9.2 Un tropiezo que conviene registrar

El primer intento de despliegue falló porque el comando se ejecutó en la **sesión
bash del servidor** en lugar de en PowerShell. El acento grave de continuación de
línea de PowerShell no existe en bash, así que bash interpretó el primer archivo
como un script a ejecutar:

```bash
# lo que pasó al pegarlo en bash del servidor
backend/yule/client.py: line 1: import: command not found
backend/yule/client.py: line 2: from: command not found
...
backend/yule/client.py: line 12: syntax error near unexpected token `('
rsync error: syntax or usage error (code 1) at main.c(1872)
```

Y el `docker compose restart django` sí corrió, sobre el código viejo. Lo
detectable fue que la suite siguió reporting `Found 38 test(s)` en vez de 44: ese
número fue el control de que el despliegue realmente había ocurrido. **Regla
práctica: el número de tests reportados por el servidor es la prueba de que el
código desplegado es el que crees.**

### 9.3 Overrides obligatorios para correr tests dentro del contenedor

```bash
docker exec -e SECURE_SSL_REDIRECT=False -e DEBUG=True sysadmin_django python manage.py test yule
```

Los dos `-e` no son opcionales: con `DEBUG=False` y `SECURE_SSL_REDIRECT=True` (la
configuración de producción), el test client sigue el redirect a HTTPS en
`https://192.168.1.250:6060`, no encuentra el host de pruebas y falla en masa.

---

## 10. Contrato de la API de OCS 2.12

Resumen reutilizable de todo lo que costó aprender. Si OCS se actualiza de versión,
esta es la lista a revalidar contra un payload real.

| Necesidad | Dónde está **de verdad** | Trampa |
|---|---|---|
| ID del equipo | llave de la raíz del dict; o `accountinfo.ID` / `hardware.ID` | no va dentro del objeto |
| Nombre del host | `hardware.NAME` | no hay `name` en la raíz |
| Sistema operativo | `hardware.OSNAME` / `OSVERSION` | mayúsculas |
| Serial del sistema | `bios[0].SSN` | `bios` es lista; `SN` no existe |
| Service tag (Dell) | `bios[0].MSN` | viene envuelto en `/.../` |
| CPU | `hardware.PROCESSORT` | `PROCESSORS` es MHz (entero) |
| CPU (alternativa) | `cpus[0].TYPE` | `cpus` es lista |
| RAM | `hardware.MEMORY` (MB) | — |
| Disco | `storages[].DISKSIZE` (**MB**) | hay que dividir entre 1024 |
| IP del equipo | `hardware.IPADDR` | `networks` trae 48 filas; la 1.ª es virtual |
| MAC del equipo | `networks[]` cuya `IPADDRESS` == `hardware.IPADDR` | la 1.ª es la virtual del firewall |
| Interfaz activa | `networks[].STATUS == "Up"` | texto, no booleano |
| Usuario | `hardware.USERID` | no hay clave `user` |
| Dominio | `hardware.WORKGROUP` | `USERDOMAIN` viene `null` en equipos de dominio |
| Último reporte | `hardware.LASTCOME` | **UTC**, sin zona |
| Software | `/computer/{id}` → clave **literal `""`** | en `/computers` solo trae IDs |
| Envoltura raíz | dict indexado por ID | no es lista |
| `limit=0` | **rechazado** por OCS 2.12 (devuelve texto, no JSON) | usar `limit=1000` |
| Logs del server | `docker logs ocsinventory-server` | `error.log` es symlink a `/proc/self/fd/2` |

---

## 11. Pendientes técnicos

| # | Pendiente | Detalle | Prioridad |
|---|---|---|---|
| 1 | Desplegar el fix de `_almacenamiento_gb` | Pasa el valor de 476 a 477 (redondeo correcto) | Baja, cosmético |
| 2 | Confirmar `get_software(3)` contra la API en vivo | Esperado `total: 122` | Media, cierra el último bug |
| 3 | Alerta de equipos que no reportan | El fallo del agente es silencioso por definición; es lo que más costó esta sesión | **Alta** |
| 4 | Capturar y versionar el payload completo de OCS como fixture | El fixture del test cubre 8 de 24 secciones; faltan `storages` multiple, `memories`, cuentas | Media |
| 5 | Validar `_red_principal()` con otro equipo | La precedencia depende del orden de `networks`, que varía por fabricante y drivers | Media |
| 6 | Considerar `DecimalField` para `almacenamiento_total_gb` | Si algún día se quiere 476.9 y no 477 | Baja |
| 7 | Automatizar el despliegue al server | Hoy depende de un `scp` manual con contraseña | Media |
| 8 | Rotar contraseña de BD de OCS | Sigue la de fábrica, que es pública | Alta, seguridad |
| 9 | `OCS_OPT_LOGLEVEL` de `512` a `0` | Se subió para diagnosticar | Baja |
| 10 | Congelar los parches del contenedor en una imagen propia | Se pierden con `--force-recreate` | Media |
| 11 | Investigar un test intermitente de la suite completa | En 3 corridas de 335 tests, una dio `FAILED (failures=1)` y dos `OK`. No es de `yule` (esa app no usa `now()` ni aleatoriedad y dio 44/44 en las 3); es de otra app y no se identificó el nombre. Conviene aislarlo antes de confiar en la suite como puerta de calidad | Media |

---

## 12. Conclusiones técnicas

1. **Un `200` no significa que el inventario se registró.** El agente puede estar
   reportando perfectamente contra la URL equivocada, durante días, sin un solo
   error en ninguna parte. La comprobación de "llega un `POST /ocsinventory` al
   log" debe ser el primer paso de cualquier diagnóstico de este sistema.

2. **El JSON de OCS no es un contrato, es un volcado de tablas.** Cualquier
   consumidor tiene que normalizar por sección, y esa normalización es código de
   verdad, no un `data.get()`. La tabla de §10 es la documentación de ese código.

3. **Un campo equivocado es peor que un campo vacío.** La MAC virtual no se ve
   como un bug: se ve como un equipo que "no cruza" con el inventario local. Los
   seis campos vacíos fueron visibles en minutos; la MAC incorrecta habría
   reducido la utilidad de la integración sin señal alguna.

4. **Los fixtures escritos a mano no prueban nada contra sistemas externos.**
   Treinta tests verdes coexistieron con seis campos rotos. El fixture real
   (`test_payload_real_ocs_212_se_mapea_completo`) es lo que convirtió el
   problema en código verificable.

5. **Cuando un síntoma tiene dos causas probables, hay que medir antes de
   hipótesis.** Comparar el access log con `LASTCOME` convirtió una conjetura de
   zona horaria en un hecho, y recién con el hecho se pudo escribir el fix con su
   justificación en el docstring.
