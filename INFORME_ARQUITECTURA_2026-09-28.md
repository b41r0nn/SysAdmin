# Informe para Arquitectura: falla de inventario OCS → Yule

**Fecha de la sesión:** 2026-09-28
**Servidor:** 192.168.1.250 (Ubuntu Server 22.04, `sistemas@ubuntuserver`)
**Componentes:** OCS Inventory NG 2.12.1 (Docker) · SysAdmin/Yule (Django 4.x)
**Solicitante:** Sistemas (REDIHOS) · **Destinatario:** Arquitectura
**Estado:** **RESUELTO y verificado en producción**
**Commits:** `a1184dd` (código) · `4a9622d` (documentación) · `918001d` (previo)

> Este informe cubre el trabajo de la sesión del 2026-09-28. El historial del
> incidente desde el 2026-09-25 está en `INFORME_OCS_YULE_2026-09-25.md` (sección 0
> resume esta misma resolución). La referencia operativa para los equipos cliente
> es `MANUAL_AGENTE_OCS.md`.

---

## 1. Resumen ejecutivo

Al final de la sesión el inventario está **completo y verificado extremo a extremo**:
un agente Windows real reporta a OCS y Yule consume y muestra todos los campos.

| Componente | Antes de la sesión | Después |
|---|---|---|
| Agente → OCS | 0 equipos registrados | 1 equipo real, `POST /ocsinventory` → `200` |
| Yule: equipos detectados | 0 (OCS vacío) | 1 |
| `serial_bios` | vacío | `F35F284` |
| `procesador` | vacío | `13th Gen Intel(R) Core(TM) i5-1335U [10 core(s) x86_64]` |
| `ip_address` | vacío | `192.168.1.137` |
| `mac_address` | `00:09:0F:AA:00:01` (**virtual, inútil**) | `E8:CF:83:0A:8C:0E` (física) |
| `usuario_dominio` | vacío | `redihossas.local\Sistemas` |
| `almacenamiento_total_gb` | vacío (fijo en `None`) | `476` |
| `ultimo_reporte_ocs` | `2026-09-29 01:27:57+00` (**5 h corrido**) | `2026-09-28 20:27:57+00` |
| Software por equipo | **vacío en todos** (bug silencioso) | pendiente de confirmar (esperado 122) |
| Tests | 30/30 yule (con parser roto) | 44/44 yule · 335/335 suite |

**Dos causas raíz independientes**, y ninguna era un defecto del servidor OCS:

1. **El agente no reportaba.** Apuntaba a una ruta que no es el receptor de
   inventarios. El servidor nunca recibió tráfico, así que no había nada que
   fallar. Detalle en §3.
2. **El parser de Yule asumía un esquema que OCS 2.12 no tiene.** Al llegar el
   primer inventario real, seis campos se guardaron vacíos o equivocados y el
   software salió vacío en todos los equipos. Detalle en §4, §5 y §6.

**El hallazgo más relevante para Arquitectura es de proceso, no de código:** el
equipo llevaba días depurando el servidor con 14 hipótesis cuando el defecto real
se resolvía mirando una línea del access log. Y la suite de tests estaba en verde
con un parser que no funcionaba contra producción, porque los fixtures de prueba
se inventaron en lugar de copiarse de la respuesta real. Ambos puntos están
desarrollados en §7 y §11.

---

## 2. Alcance de la sesión

**Objetivo:** que un equipo cliente reportara inventario y que Yule mostrara todos
los campos del modelo.

**En alcance:** configuración del agente Windows, mapeo del JSON de OCS 2.12 al
modelo de Yule, corrección de zona horaria, documentación para el despliegue
masivo y cierre del informe técnico.

**Fuera de alcance (pendientes, sin tocar):** endurecimiento del stack OCS
(rotación de credenciales, `OCS_OPT_LOGLEVEL`, persistencia de parches),
backup al NAS y las optimizaciones de `forms.py` que arrastrábamos de antes.

---

## 3. Problema 1 — el agente no reportaba (causa raíz del incidente)

### 3.1 Síntoma

El panel de OCS mostraba `Total: 0 equipos detectados` y la tabla `hardware` vacía,
con el stack Perl parcheado y la API respondiendo `200`. El panel de Yule tampoco
mostraba nada.

### 3.2 Lo que se había asumido

Que el receptor de inventarios estaba roto. De ahí vinieron 14 hipótesis (H1-H13
más el test de descarte de H14) sobre módulos Perl faltantes, esquema de base de
datos y formato del XML, documentadas en el informe del 25.

### 3.3 Causa raíz

OCS en este servidor expone **tres rutas que no son intercambiables**:

| Ruta | Propósito | Dónde se configura |
|---|---|---|
| `/ocsinventory` | **receptor de inventarios** | el agente |
| `/ocsapi/v1` | API JSON | Yule (`/yule/configuracion/`) |
| `/ocsreports/` | panel web | el navegador |

El agente estaba configurado contra `/ocsreports` o `/ocsapi/v1`.

### 3.4 Por qué no se manifestaba como error

Es el punto que más tiempo costó y el que conviene documentar: **la confusión de
ruta no produce ningún error.** El agente hace su petición a una URL que existe y
responde `200`; simplemente nunca llega un inventario al receptor. El síntoma
—`0 equipos`— es idéntico al de un servidor roto, lo que llevó el diagnóstico en
dirección equivocada durante días.

### 3.5 La evidencia que cerró el caso

Access log de Apache del contenedor, filtrando el `POST` del receptor:

```bash
docker logs --tail 40 ocsinventory-server 2>&1 | grep "POST /ocsinventory"
```

- **Antes de corregir la URL:** ninguna línea. Nunca hubo tráfico al receptor.
- **Después de corregirla:**

```
192.168.1.137 - - [28/Sep/2026:22:27:57 +0200] "POST /ocsinventory HTTP/1.1" 200 45 "-" "OCS-NG_WINDOWS_AGENT_v2.11.0.1"
```

Esa línea, junto con la fila creada en `hardware` (ID `3`), demuestra que el
servidor estaba sano y lo que faltaba era tráfico.

### 3.6 El `500` con XML sintético era un falso positivo

El `POST` de prueba con `<OCS/>` creaba la fila en `hardware` a medias y devolvía
`500`, lo que se interpretó como evidencia de un bug de ingesta. **Era un artefacto
de la prueba**: el XML no traía la sección `hardware` poblada, así que la fila se
creaba vacía y falla al digerir. Un agente real envía el XML completo. Las
hipótesis H1-H13 y el test de descarte de H14 quedan retiradas.

### 3.7 Corrección aplicada

Reinstalación limpia del agente (QSA "service", modo red) con la URL
`http://192.168.1.250:8081/ocsinventory`, verificado con `POST` → `200` y con la
fila en OCS. Procedimiento repeatable documentado en `MANUAL_AGENTE_OCS.md`.

---

## 4. Problema 2 — Yule guardaba campos vacíos por un esquema distinto

Con el primer inventario real, seis campos no se poblaron. **El JSON de OCS 2.12 es
un volcado directo de las tablas, sin un esquema unificado**: cada sección tiene
la forma de la tabla de la que viene y los nombres de columna son los de la base
de datos, en mayúsculas.

### 4.1 El payload real (evidencia)

Extraído de `GET /ocsapi/v1/computers?limit=1`:

```json
{
  "3": {
    "accountinfo": { "ID": 3 },
    "bios":  [ { "HARDWARE_ID": 3, "SSN": "F35F284", "MSN": "/F35F284/VNWSV0051K0C5N/", "SMODEL": "Latitude 3450" } ],
    "cpus":  [ { "TYPE": "13th Gen Intel(R) Core(TM) i5-1335U", "MANUFACTURER": "GenuineIntel" } ],
    "hardware": {
      "ID": 3, "NAME": "W11F35F", "IPADDR": "192.168.1.137",
      "USERID": "Sistemas", "USERDOMAIN": null, "WORKGROUP": "redihossas.local",
      "LASTCOME": "2026-09-28 20:27:57", "MEMORY": 16288,
      "OSNAME": "Microsoft Windows 11 Pro", "OSVERSION": "10.0.26200",
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

La sección `networks` tiene **48 entradas** en un portátil con firewall integrado.

### 4.2 Los seis defectos y su corrección

| # | Campo | Síntoma | Causa | Corrección | Ubicación |
|---|---|---|---|---|---|
| 1 | `serial_bios` | vacío | `bios` es **lista**, no dict, y el serial del sistema está en `SSN`, no en `SN` | `_section()` acepta listas; se lee `SSN` con fallback a `SN`/`MSN` | `sync.py:_section`, `_extract_equipo_data` |
| 2 | `procesador` | vacío | `hardware.PROCESSORS` es la **frecuencia en MHz** (entero `1300`), no el nombre | se lee `hardware.PROCESSORT`; fallback a `cpus[0].TYPE` | `sync.py:_procesador` |
| 3 | `ip_address` | vacío | se tomaba la 1.ª de 48 interfaces, que es la virtual y no tiene IP | se usa `hardware.IPADDR` y se cruza con la interfaz que la tiene | `sync.py:_red_principal` |
| 4 | `mac_address` | `00:09:0F:AA:00:01` | es la MAC de la **interfaz virtual del firewall**; inservible para cruzar contra el inventario local | MAC de la interfaz cuya IP coincide con `hardware.IPADDR` | `sync.py:_red_principal` |
| 5 | `usuario_dominio` | vacío | **no existe clave `user` en la raíz**; el usuario va en `hardware.USERID` y el dominio en `hardware.WORKGROUP` | se compone `redihossas.local\Sistemas` | `sync.py:_extract_equipo_data` |
| 6 | `almacenamiento_total_gb` | vacío | el campo estaba fijo en `None` con el comentario "OCS no siempre proporciona esto" | se calcula desde `storages.DISKSIZE` (viene en MB) | `sync.py:_almacenamiento_gb` |

El defecto 4 es el más relevante a futuro: una MAC equivocada no produce un campo
vacío, produce un **falso negativo silencioso** en el cruce con el inventario local
(`buscar_posibles_matches()`), que es justamente la función que vale la pena tener
correcta.

### 4.3 Precedencia implementada en `_red_principal()`

Para no depender de que la interfaz virtual venga siempre primera:

1. La interfaz cuyo `IPADDRESS` coincide con `hardware.IPADDR` (**preferida**).
2. La primera con `STATUS` = `Up` y MAC no nula.
3. La primera con MAC no nula.

La IP se resuelve por separado, porque la interfaz de management suele tener MAC
pero no IP: `hardware.IPADDR` primero, y si faltara, la primera IP no vacía.

---

## 5. Problema 3 — el software salía vacío en todos los equipos

Este no se había detectado porque nadie lo miró: el panel de Yule se veía normal sin
inventario, así que "sin software" no era un síntoma visible.

**Causa:** `get_software()` buscaba la clave `"software"` en la respuesta de
`/computer/{id}`. La forma real es:

```json
{ "3": { "": [ { "NAME": "Google Chrome", "VERSION": "140.0", "PUBLISHER": "Google LLC" } ] } }
```

La sección llega bajo la **clave literal vacía `""`**. El parser devolvía `[]`
siempre, para todos los equipos, sin error ni warning.

**Corrección:** `_find_software_rows()` recorre la respuesta y toma la primera
lista de filas que tengan nombre y versión, en lugar de buscar una clave fija.
Hay un test que garantiza que no confunde la lista de software con otras secciones
que también son listas (`memories`, `monitors`).

**Verificación pendiente:** el comando para confirmarlo contra la API en vivo está
en §13. Esperado: `total: 122`.

---

## 6. Problema 4 — `ultimo_reporte_ocs` con 5 horas de desfase

**Síntoma:** Yule mostraba `2026-09-29 01:27:57+00` para un inventario recibido a
las `20:27:57` del día 28. Una diferencia de exactamente 5 horas, la de
America/Bogota frente a UTC.

**Diagnóstico:** dos fuentes independientes coincidían en el mismo instante:

| Fuente | Valor |
|---|---|
| Access log de Apache | `28/Sep/2026:22:27:57 +0200` → `20:27:57 UTC` |
| `hardware.LASTCOME` en la BD | `2026-09-28 20:27:57` |

**Causa:** OCS escribe `LASTCOME` con `NOW()` evaluado por el servidor de base de
datos, que corre en **UTC**, y lo devuelve como hora naive sin zona. El parser lo
trataba como hora local del servidor Django.

**Corrección:** `_parse_ocs_datetime()` marca la hora naive como UTC en lugar de
usar `timezone.get_current_timezone()`, con el razonamiento documentado en el
docstring para que nadie lo revierta.

**Efecto secundario favorable:** con la fecha correcta, la UI deja de mostrar
"reportó ahora" para equipos que nunca han reportado, que era el defecto original
del campo (usaba `datetime.now()`).

---

## 7. Por qué 30 tests en verde no detectaron ninguno de estos defectos

Este es el hallazgo de proceso que más recomiendo revisar, y es la razón por la que
esta sección existe.

Los tests anteriores pasaban (`tests yule: 30/30` en el commit `918001d`) con un
parser que fallaba en 6 campos frente a producción. La causa: **los fixtures de
prueba se escribieron a mano en lugar de copiarse de una respuesta real.**

| Test | Fixture inventado | Forma real de OCS 2.12 |
|---|---|---|
| `test_software_desde_dict_indexado_por_id` | `{"1": {"software": [...]}}` | `{"3": {"": [...]}}` |
| `test_lee_claves_en_mayusculas` | `"BIOS": {"SN": "ABC123"}` | `"bios": [{"SSN": "F35F284"}]` |
| `test_lee_claves_en_mayusculas` | `"PROCESSORS": {"NAME": "Intel..."}` | `"PROCESSORS": 1300` + `"PROCESSORT": "..."` |

Un test que pasa porque el fixture se escribió para satisfacer el código no prueba
nada sobre la integración. Los tres fixtures anteriores siguen en la suite
(`backend/yule/tests.py:351`, `:375`, `:377`) **junto a** el nuevo fixture real
(`test_payload_real_ocs_212_se_mapea_completo`, línea ~469), que sí cubre el
payload completo de OCS 2.12 y fue el que cerró los seis defectos de §4.

**Recomendación:** que cualquier test de integración contra una API externa se
escriba a partir de una respuesta capturada, y que la captura se versione como
fixture. Es la única forma de que el test detecte derivas del contrato.

---

## 8. Cambios de código

### 8.1 `backend/yule/sync.py` (249 líneas cambiadas)

Seis helpers nuevos o modificados, todos con el *por qué* documentado:

| Función | Tipo | Responsabilidad |
|---|---|---|
| `_get_ci()` | modificada | Lectura de claves sin distinguir mayúsculas (las columnas de OCS vienen en mayúsculas) |
| `_section()` | modificada | Normaliza dict, dict anidado por ID y **lista** a un dict plano |
| `_lista()` | nueva | Normaliza secciones 1-a-N (`networks`, `storages`, `cpus`) a lista de dicts |
| `_red_principal()` | nueva | Empareja `hardware.IPADDR` con la interfaz física y devuelve `(mac, ip)` |
| `_procesador()` | nueva | `PROCESSORT` → `cpus[0].TYPE` → `PROCESSORS` si fuese lista |
| `_almacenamiento_gb()` | nueva | `storages[].DISKSIZE` (MB) → GB |
| `_parse_ocs_datetime()` | modificada | `LASTCOME` se interpreta como UTC |
| `_extract_equipo_data()` | modificada | ID desde `accountinfo.ID`/`hardware.ID`; usuario desde `USERID`+`WORKGROUP` |

### 8.2 `backend/yule/client.py` (79 líneas cambiadas)

| Cambio | Detalle |
|---|---|
| `_computers_from_payload()` | Inyecta `id` desde la clave del dict: OCS 2.12 **no** pone el ID dentro del objeto, y como `id_ocs` es `unique=True` sin él todos los equipos se colapsaban en un mismo registro |
| `_find_software_rows()` (nueva) | Localiza la sección de software bajo la clave `""` |
| `get_software()` | Usa el helper anterior; se eliminan las cuatro ramas de detección de forma que se reemplazaron |

### 8.3 `backend/yule/tests.py` (247 líneas cambiadas)

6 tests nuevos, entre ellos `test_payload_real_ocs_212_se_mapea_completo`, que
valida los 12 campos del modelo contra el payload real completo, y
`test_lastcome_se_interpreta_como_utc`, que fija la decisión de zona horaria para
que no se revierta.

---

## 9. Verificación

### 9.1 En producción (server `192.168.1.250`)

```
docker exec -e SECURE_SSL_REDIRECT=False -e DEBUG=True sysadmin_django python manage.py test yule
→ Ran 44 tests ... OK

docker exec sysadmin_django python manage.py sync_ocs --force
→ Sincronización exitosa: 1 detectados, 0 nuevos, 1 actualizados, 0 desaparecidos
```

Estado resultante de `yule_equipoocs`:

| Campo | Valor |
|---|---|
| `id_ocs` | `3` |
| `nombre_host` | `W11F35F` |
| `usuario_dominio` | `redihossas.local\Sistemas` |
| `so_nombre` / `so_version` | `Microsoft Windows 11 Pro` / `10.0.26200` |
| `serial_bios` | `F35F284` |
| `mac_address` | `E8:CF:83:0A:8C:0E` |
| `ip_address` | `192.168.1.137` |
| `procesador` | `13th Gen Intel(R) Core(TM) i5-1335U [10 core(s) x86_64]` |
| `memoria_ram_mb` | `16384` |
| `almacenamiento_total_gb` | `476` |
| `ultimo_reporte_ocs` | `2026-09-28 20:27:57+00` |

### 9.2 Local

- `manage.py test yule` → **44/44 OK**
- Suite completa → **335/335 OK**

### 9.3 En OCS

Fila en `hardware` ID `3`, con `bios` 1, `networks` 48 y `software` 122.

---

## 10. Cronología de la sesión

| # | Hecho | Evidencia |
|---|---|---|
| 1 | Se reinstala el agente con la URL `/ocsinventory` | `POST /ocsinventory` → `200` |
| 2 | Aparece el equipo `W11F35F` en OCS (ID 3) | tabla `hardware` |
| 3 | Yule detecta 1 equipo, pero con 5 campos vacíos y la MAC virtual | `sync_ocs` + consulta a `yule_equipoocs` |
| 4 | Se obtiene el payload real y se contrasta contra el parser | `GET /ocsapi/v1/computers?limit=1` |
| 5 | Se identifican 6 defectos de esquema en el parser | §4 |
| 6 | Se detecta además el software vacío y el desfase de 5 h | §5, §6 |
| 7 | Se implementan las correcciones con 6 tests nuevos | `a1184dd` |
| 8 | Se despliega vía `scp` (no hay rsync en el equipo de trabajo) | 44/44 en el server |
| 9 | Se sincroniza y se verifican los 12 campos | §9.1 |
| 10 | Se documenta el incidente y se publica el manual del agente | `4a9622d` |

---

## 11. Deuda técnica y riesgos

| # | Riesgo | Impacto | Mitigación actual | Esfuerzo |
|---|---|---|---|---|
| R1 | `OCS_OPT_LOGLEVEL` quedó en `512` (se subió para diagnosticar) | Log verboso en producción, ruido y riesgo de exponer datos en disco | Pendiente: volver a `0` | Bajo |
| R2 | Contraseña de la BD de OCS es la de fábrica, que es pública | Anyone con acceso a la red del servidor puede leer el inventario completo | Pendiente: rotación + variáveis de entorno | Bajo |
| R3 | Parches de Perl/PHP aplicados a mano dentro del contenedor | Se pierden con `--force-recreate`; el receptor y el panel quedan rotos sin avisar | `patch_ocs_server.sh` idempotente, pero manual | Medio: construir imagen propia |
| R4 | Ningún proceso falla visiblemente si el agente deja de reportar | El síntoma es silencioso y pasó días sin detectarse | Ninguno. Es la causa raíz del incidente | **Alto: alerta de "no reporta hace N días"** |
| R5 | El JSON de OCS no tiene esquema estable entre versiones | Un upgrade de OCS puede romper el parser silenciosamente | Documentado en `OCS_INVENTORY_SETUP.md` con el payload real | Bajo |
| R6 | No hay ruta de despliegue automatizada al server | Cada fix depende de un `scp` manual con contraseña; ya costó una vuelta por un comando corrido en el shell equivocado | Ninguno | Medio: clave SSH o `docker compose` por pipeline |
| R7 | El cruce con el inventario local depende de serial y MAC | Con la MAC virtual el cruce fallaba en silencio | Corregido en esta sesión | Bajo |
| R8 | `forms.py:48-54` oculta los errores de `set_ocs_password()` | Un fallo de conexión a OCS se presenta como "guardado" sin mensaje | Ninguno. Preexistente, ajeno a esta sesión | Bajo |

**R4 es el riesgo que recomiendo priorizar.** La lección del incidente es que
tanto OCS como Yule fallan en silencio: cero equipos, campos vacíos y ninguna
alerta. Una comprobación tipo "hay equipos en OCS que no reportan desde hace más
de N días" habría detectado el problema el primer día.

---

## 12. Recomendaciones para Arquitectura

1. **Validar el camino completo antes de depurar el servidor.** Ante "no hay
   inventarios", la primera comprobación debe ser si llega un `POST` al receptor,
   no la salud del stack. El orden correcto es: (a) ¿hay tráfico en el log?
   (b) ¿el agente apunta a la ruta correcta? (c) ¿el servidor responde? Ese
   orden habría resuelto este incidente en minutos en lugar de días.
2. **Fixtures de integración desde respuestas reales.** Ningún test de integración
   con una API externa debería escribirse a mano (§7). Adjunto de ejemplo:
   `test_payload_real_ocs_212_se_mapea_completo`.
3. **Tratar las fechas de OCS como UTC por contrato.** `LASTCOME` no trae zona y
   depende del `NOW()` de la BD. Queda documentado en el código con su evidencia.
4. **Alertas de inventario envejecido** (R4). Es la mitigación que convierte un
   fallo silencioso en un incidente visible.
5. **Inmutable el stack OCS.** Construir una imagen propia con los parches ya
   aplicados elimina R3 y hace que `--force-recreate` sea seguro.
6. **Hacer obligatoria la rotación de credenciales de fábrica** en la instalación
   inicial de cualquier servicio nuevo (R2).
7. **Automatizar el paso a producción** (R6) o, en su defecto, documentar el
   procedimiento con la ruta correcta por sistema operativo.

---

## 13. Pendientes

### 13.1 Verificación inmediata

```bash
docker exec sysadmin_django python manage.py shell -c "from yule.client import build_client; s=build_client().get_software(3); print('total:', len(s)); print(s[:3])"
```

Esperado: `total: 122` con `Google Chrome` entre los primeros. Antes del fix
devolvía `0`.

### 13.2 Operaciones (sin cambios de código)

| # | Pendiente | Comando / referencia |
|---|---|---|
| 1 | `OCS_OPT_LOGLEVEL` a `0` | Editar la config de Apache del contenedor OCS |
| 2 | Rotar contraseña de la BD de OCS | Actualizar usuario, `.env` de Yule y la variable del contenedor |
| 3 | Backup de SysAdmin al NAS | Falta IP, usuario, ruta y credenciales |
| 4 | Reprobar parches tras cualquier recreación del contenedor | `bash patch_ocs_server.sh` |

### 13.3 Con el próximo equipo que se conecte

Validar con un equipo real adicional que el parser se comporta igual (sobre todo
`_red_principal()`, que depende del número y orden de interfaces de red del
equipo) y que el cruce contra el inventario local encuentra el activo por serial.

---

## 14. Anexos — comandos de verificación

Todos reproducibles. El primero es el que habría resuelto el incidente.

```bash
# 1. ¿Llega tráfico al receptor de inventarios?  (si esto no da líneas, el problema NO es del server)
docker logs --tail 40 ocsinventory-server 2>&1 | grep "POST /ocsinventory"

# 2. ¿El equipo está en OCS y con secciones pobladas?
docker exec ocsinventory-db sh -c 'mysql -u"$OCS_DB_USER" -p"$OCS_DB_PASS" ocsweb -e "SELECT h.ID, h.NAME, h.LASTCOME, (SELECT COUNT(*) FROM bios b WHERE b.HARDWARE_ID=h.ID) AS bios, (SELECT COUNT(*) FROM networks n WHERE n.HARDWARE_ID=h.ID) AS redes, (SELECT COUNT(*) FROM software s WHERE s.HARDWARE_ID=h.ID) AS software FROM hardware h ORDER BY h.LASTCOME DESC;"'

# 3. Payload real de la API (fuente de la verdad para el parser)
curl -s -u "$U:$P" "http://192.168.1.250:8081/ocsapi/v1/computers?limit=1" | head -c 2000

# 4. Qué guardó Yule
docker exec sysadmin_db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -x -c "SELECT id_ocs,nombre_host,usuario_dominio,so_nombre,so_version,serial_bios,mac_address,ip_address,procesador,memoria_ram_mb,almacenamiento_total_gb,ultimo_reporte_ocs FROM yule_equipoocs;"'

# 5. Tests (los overrides evitan el redirect a HTTPS en el test client)
docker exec -e SECURE_SSL_REDIRECT=False -e DEBUG=True sysadmin_django python manage.py test yule

# 6. ¿El agente está instalado y reportando en el equipo cliente?
Get-Service "OCS Inventory Service"          # Windows: debe estar Running
Get-Content "C:\ProgramData\OCS Inventory NG\Agent\ocsinventory.ini" | Select-String Server
```

Las variables `U` y `P` del anexo son las de la API OCS y se toman del `.env` del
servidor; no están en el repositorio.

---

## 15. Archivos de referencia

| Archivo | Contenido |
|---|---|
| `MANUAL_AGENTE_OCS.md` | Procedimiento de instalación y configuración del agente (lo que se entrega a Sistemas para el despliegue masivo) |
| `INFORME_OCS_YULE_2026-09-25.md` | Historial del incidente e informe técnico original; sección 0 con la resolución |
| `OCS_INVENTORY_SETUP.md` | Topología del servidor OCS, trampas del formato de la API 2.12, comandos de uso diario |
| `AGENTS.md` | Contexto operativo del repo, causa raíz y pendientes |
| `backend/yule/sync.py` | Parser de inventario (los 6 helpers de §8.1) |
| `backend/yule/tests.py` | Fixtures reales y tests de integración (§7) |
| `patch_ocs_server.sh` | Reaplica los parches efímeros del contenedor OCS |
