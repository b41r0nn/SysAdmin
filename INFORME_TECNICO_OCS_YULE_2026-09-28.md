# Análisis técnico: por qué OCS no registraba inventario y por qué Yule guardaba campos vacíos

**Sesión:** 2026-09-28
**Servidor:** 192.168.1.250 · Ubuntu Server 22.04 · Docker Compose
**Componentes:** `ocsinventory/ocsinventory-docker-image:2.12.1` + SysAdmin/Yule (Django)
**Destinatario:** Arquitectura
**Estado:** resuelto y verificado en producción (incluye el fix de software
verificado contra la API en vivo el 2026-09-28)
**Código:** `918001d` → `a1184dd` → `48e6080` → fix de software · **Docs:** `4a9622d`

> Documento gemelo de gestión: `INFORME_ARQUITECTURA_2026-09-28.md` (visión de
> negocio y riesgos). Este documento es la referencia técnica: flujo de datos,
> anatomía de la respuesta de OCS y el antes/después de cada función con el
> código real. Procedimiento para los equipos cliente: `MANUAL_AGENTE_OCS.md`.
>
> **Revisión 2 (2026-09-28).** La §5 fue reescrita tras verificar contra la API
> en vivo: la primera versión afirmaba que la clave `"software"` no existía y
> daba por correcta una función que mezclaba 18 secciones distintas. El texto
> original se conserva resumido y marcado como error, porque el caso es
> instructivo.

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

## 5. Fase 4 — el software

Esta sección se corrigió **después** de verificar contra la API en vivo, el
2026-09-28. La primera versión de este informe afirmaba dos cosas que
resultaron falsas; se señalan como tales porque el error es instructivo.

### 5.1 Lo que realmente devuelve `/computer/{id}`

El software aparece **dos veces** en la misma respuesta, con dos formas
distintas:

```json
{ "3": {
    "":         [ { "NAME": "Google Chrome", "VERSION": "153.0", "PUBLISHER": "Google LLC" } ],
    "software": [ { "NAME_ID": 1, "VERSION_ID": 2, "PUBLISHER_ID": 3, "HARDWARE_ID": 3 } ]
} }
```

- La clave **literal vacía `""`** trae los nombres y versiones ya resueltos.
- La clave **`"software"`** trae solo IDs, sin textos.

> **Corrección a la primera versión de este informe.** Se afirmaba que la clave
> `"software"` "no existe". Es falso: existe, y es la que el parser original
> buscaba. El problema real es que esa clave trae `NAME_ID`, no `NAME`, así que
> leerla producía una lista de nombres vacíos. La clave `""` es la que sirve
> para mostrar software.

### 5.2 El defecto original

El parser de la primera versión buscaba `data["software"]` y, al no encontrar
nombres, devolvía `[]` para todos los equipos, sin error ni warning:

```python
# ANTES (código original)
if isinstance(data, dict) and "software" in data:
    raw = data["software"]          # trae NAME_ID, no NAME -> nombres vacíos
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

### 5.3 El error que Almost se cuela en producción

Una primera corrección buscó la sección "estructuralmente": recorría la respuesta
acumulando **todas** las listas y devolvía la unión en cuanto encontraba una fila
con nombre y versión. Parecía correcta, y los tests pasaban. Era incorrecta.

`/computer/3` devuelve **18 secciones**, y varias tienen clave `name`:

| Sección | Filas | | Sección | Filas |
|---|---|---|---|---|
| `""` | 122 | | `inputs` | 5 |
| `software` | 122 | | `ports` | 5 |
| `networks` | 48 | | `sounds` | 5 |
| `printers` | 8 | | `memories` | 2 |
| `controllers` | 7 | | `monitors` | 2 |
| `slots` | 7 | | `bios`/`cpus`/`storages`/... | 1 c/u |

Acumular todas daba **340 filas**, y el filtro final por nombre dejaba **157**:
122 de software más **35 elementos que no son software**:

```
Intel(R) Iris(R) Xe Graphics          Realtek Audio
NVMe EG6 KIOXIA 512GB                  USB Audio Device
Kyocera ECOSYS M3655idn KX (impresora) EPSON LX-350 ESC/P
Microsoft Print to PDF                AnyDesk Printer
Ranura de sistema (x7)                None (x5)
```

**Esto no lo detectó ningún test**, porque el fixture de tests tenía una sola
sección de software y dos secciones sin `name`. Faltaba el caso real.

### 5.4 La corrección definitiva

Devolver **las filas de la sección de software**, no la unión de todas:

```python
@staticmethod
def _find_software_rows(data: Any) -> List[Dict[str, Any]]:
    """Localiza las filas de la sección de software de `/computer/{id}`."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    root = OCSClient._unwrap_computer(data)   # quita la envoltura {"3": {...}}
    if not root:
        return []

    def filas_de(valor: Any) -> List[Dict[str, Any]]:
        if not isinstance(valor, list):
            return []
        return [item for item in valor if isinstance(item, dict)]

    def parece_software(filas: List[Dict[str, Any]]) -> bool:
        for item in filas:
            keys = {str(k).lower() for k in item}
            if "name" in keys and ("version" in keys or "publisher" in keys):
                return True
        return False

    # 1) Claves que usa OCS para el software, en orden de preferencia.
    for clave in ("", "software"):
        filas = filas_de(root.get(clave))
        if filas and parece_software(filas):
            return filas

    # 2) Respaldo para otras versiones de OCS: la primera lista con nombre y
    #    versión. El camino normal (1) no depende de esta heurística.
    for valor in root.values():
        filas = filas_de(valor)
        if filas and parece_software(filas):
            return filas

    return []
```

El camino principal (1) es **determinista**: prueba la clave `""` y la clave
`"software"` en orden. La heurística (2) queda solo como respaldo para versiones
de OCS donde la clave nombreada no exista.

**Verificación contra el payload real de `/computer/3`:**

| | Filas devueltas | Con nombre |
|---|---|---|
| Código con la unión de listas | 340 | **157** (35 ajenas) |
| Código corregido | 122 | **122** |

122 coincide con `SELECT COUNT(*) FROM software WHERE HARDWARE_ID=3` en la base
de datos de OCS, y 118 nombres distintos con `COUNT(DISTINCT NAME_ID)` — los 4
repetidos son datos propios de OCS (mismo producto en variantes de 32/64 bits),
no un error del parser.

### 5.5 Dónde se manifiesta el bug en la aplicación

`get_software()` no lo usa el `sync_ocs`, sino el flujo de mantenimiento:

- `mantenimiento/services.py:40` — `snapshot_software_ocs(activo)`
- `mantenimiento/views.py:311` — al **abrir** "Documentar mantenimiento" precarga
  el textarea con los nombres
- `mantenimiento/views.py:288` — al **guardar**, si el textarea quedó vacío,
  persiste esos nombres en `OrdenMantenimiento.software_snapshot`
- `mantenimiento/services.py:98` — esos nombres salen en la **hoja de vida PDF**

Con el bug, el formulario se precargaba con 157 líneas incluyendo la impresora
Kyocera, la tarjeta de sonido y siete "Ranura de sistema", y quedaban guardadas
en la orden de mantenimiento.

**En producción no hay datos contaminados**: al momento de la corrección había una
sola orden con software (`["Chrome", "PDF24"]`, escrita a mano) y **ningún activo
estaba vinculado a un equipo OCS**, así que el auto-snapshot nunca se había
disparado. El bug era latente, no visible.

### 5.6 Lo que este caso enseña

1. La clave `"software"` **sí existe**; la clave `""` también. Ninguna de las dos
   suposiciones ("solo existe la vacía" / "solo existe software") era correcta.
2. Un acumulador de candidatos que devuelve **la unión** en vez de **la lista
   ganadora** parece correcto y falla en silencio, especialmente cuando muchas
   secciones comparten el mismo nombre de campo.
3. Un test con un fixture de dos secciones no representa una respuesta de 18. El
   fixture tiene que ser una captura real, completa.

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

Verificado por SSH directo sobre `192.168.1.250` con clave (`sistemas@`), el
2026-09-28. `/opt/sysadmin/app` **no es un clon de git** (no tiene `.git`): es
una copia de archivos, así que el despliegue es `scp`, no `git pull`.

```bash
docker exec -e SECURE_SSL_REDIRECT=False -e DEBUG=True sysadmin_django python manage.py test yule
# Found 46 test(s). Ran 46 tests ... OK

docker exec -e SECURE_SSL_REDIRECT=False -e DEBUG=True sysadmin_django python manage.py test
# Found 337 test(s). Ran 337 tests ... OK

docker exec sysadmin_django python manage.py sync_ocs --force
# Sincronización exitosa: 1 detectados, 0 nuevos, 1 actualizados, 0 desaparecidos
```

Estado de `yule_equipoocs` **después** del despliegue del fix de almacenamiento:

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
almacenamiento_total_gb | 477          <- antes 476 (redondeo correcto)
ultimo_reporte_ocs      | 2026-09-28 20:49:44+00
```

`get_software(3)` contra la API en vivo, en producción:

| | Filas devueltas | Con nombre |
|---|---|---|
| Antes del fix de §5.4 | 340 | **157** (35 ajenas al software) |
| Después del fix | 122 | **122** |

### 8.2 Local

| Suite | Resultado |
|---|---|
| `manage.py test yule` | 46/46 OK |
| `manage.py test` (completa) | 337/337 OK |

### 8.3 En OCS

Fila `hardware` ID `3`. Conteos reales en la base de datos de OCS:

```sql
SELECT COUNT(*) FROM software WHERE HARDWARE_ID=3;              -- 122
SELECT COUNT(DISTINCT NAME_ID) FROM software WHERE HARDWARE_ID=3; -- 118
```

Las 18 secciones de `/computer/3`: `""` 122, `software` 122, `networks` 48,
`printers` 8, `controllers` 7, `slots` 7, `inputs` 5, `ports` 5, `sounds` 5,
`memories` 2, `monitors` 2, y siete secciones de una fila.

### 8.4 Lo que sigue sin resolver

- `W11F35F` **no tiene match** con ningún activo del inventario local
  (`verificar_equipos_sin_match()` lo reporta; 0 de 24 activos con
  `equipo_ocs`). El software de OCS no llega a ninguna hoja de vida mientras tanto.
- Un test intermitente de otra app: 1 de 3 corridas de la suite completa dio
  `FAILED (failures=1)`. No se identificó cuál.

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
| Software | `/computer/{id}` → clave **literal `""`** (con `NAME`/`VERSION`) | en `/computers` solo trae `NAME_ID` |
| Software (2.ª copia) | `/computer/{id}` → clave `"software"` | trae `NAME_ID`, **no** `NAME`: no sirve para mostrar |
| Secciones de `/computer/{id}` | **18 listas**: `""`, `software`, `networks`, `printers`, `controllers`, `slots`, `inputs`, `ports`, `sounds`, `memories`, `monitors`, `accountinfo`, `bios`, `cpus`, `devices`, `drives`, `storages`, `videos` | varias comparten la clave `name`: no se puede acumular todas |
| Envoltura raíz | dict indexado por ID | no es lista |
| `limit=0` | **rechazado** por OCS 2.12 (devuelve texto, no JSON) | usar `limit=1000` |
| Logs del server | `docker logs ocsinventory-server` | `error.log` es symlink a `/proc/self/fd/2` |

---

## 11. Pendientes técnicos

| # | Pendiente | Detalle | Prioridad |
|---|---|---|---|
| 1 | Alerta de equipos que no reportan | El fallo del agente es silencioso por definición; es lo que más costó esta sesión | **Alta** |
| 2 | Vincular el equipo de OCS con el inventario local | `W11F35F` sigue sin match: `verificar_equipos_sin_match()` lo reporta, y 0 de 24 activos tienen `equipo_ocs`. Hasta que no se vincule, el software de OCS no llega a ninguna hoja de vida | **Alta** |
| 3 | Capturar y versionar el payload completo de OCS como fixture | El fixture actual cubre 8 secciones; el de `/computer/{id}` tiene 18. Falta un fixture completo y real | Media |
| 4 | Validar `_red_principal()` con otro equipo | La precedencia depende del orden de `networks`, que varía por fabricante y drivers | Media |
| 5 | Rotar contraseña de BD de OCS | Sigue la de fábrica, que es pública | Alta, seguridad |
| 6 | Automatizar el despliegue al server | Resuelto con clave SSH, pero el `scp` sigue siendo manual | Media |
| 7 | Congelar los parches del contenedor en una imagen propia | Se pierden con `--force-recreate` | Media |
| 8 | Considerar `DecimalField` para `almacenamiento_total_gb` | Si algún día se quiere 476.9 y no 477 | Baja |
| 9 | `OCS_OPT_LOGLEVEL` de `512` a `0` | Se subió para diagnosticar | Baja |
| 10 | Investigar un test intermitente de la suite completa | En 3 corridas de 335 tests, una dio `FAILED (failures=1)` y dos `OK`. No es de `yule` (esa app no usa `now()` ni aleatoriedad y dio 44/44 en las 3); es de otra app y no se identificó el nombre | Media |

### Cerrados durante esta sesión

| # | Pendiente | Resultado |
|---|---|---|
| ✔ | Desplegar el fix de `_almacenamiento_gb` | 476 → 477 en producción, `int` correcto |
| ✔ | Confirmar `get_software(3)` contra la API en vivo | Detectó el bug de las 18 secciones; corregido a 122 |

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
   formular hipótesis.** Comparar el access log con `LASTCOME` convirtió una
   conjetura de zona horaria en un hecho, y recién con el hecho se pudo escribir
   el fix con su justificación en el docstring.

6. **Verificar contra el sistema real es lo que separa un fix de una suposición.**
   Cuatro correcciones de esta sesión pasaron todos los tests y una estaba mal:
   `_find_software_rows()` acumulaba las 18 listas de `/computer/{id}` y devolvía
   157 entradas en vez de 122, metiendo una impresora Kyocera, una tarjeta de
   sonido y siete "Ranura de sistema" en el inventario de software. El test
   existía y pasaba, porque el fixture tenía dos secciones en vez de dieciocho.
   La corrección no salió de leer el código, sino de comparar el resultado contra
   `SELECT COUNT(*) FROM software` en la base de datos de OCS.

7. **Un acumulador que devuelve la unión en vez de la lista ganadora es un
   bug silencioso.** La versión anterior de esa función parecía correcta y el
   filtro por nombres la hacía parecer plausible. Cuando varias secciones
   comparten nombres de campo —y en OCS eso es la norma—, la única forma segura
   es iterar sobre las claves conocidas, no buscar "la lista que parezca
   correcta".
