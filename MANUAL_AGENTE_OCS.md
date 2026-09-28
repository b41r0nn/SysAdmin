# Manual: instalación y configuración del agente OCS Inventory en los equipos cliente

**Servidor OCS:** `http://192.168.1.250:8081`
**Versión del agente probada:** `OCS-NG_WINDOWS_AGENT_v2.11.0.1` (Windows 11 Pro 24H2)
**Público:** Sistemas (REDIHOS)
**Fecha:** 2026-09-28

Este manual es el procedimiento para dejar un equipo Windows reportando inventario
a nuestro servidor OCS. Sigue los pasos en orden: el paso 1 es donde estuvo el
error que nos costó el diagnóstico.

---

## 1. La regla de oro: qué URL lleva el agente

OCS en este servidor expone **tres rutas distintas** y no son intercambiables.
Confundirlas no produce ningún error visible: el servidor responde con `200` y el
inventario simplemente nunca se registra.

| Ruta | Para qué | Dónde se configura |
|---|---|---|
| `/ocsinventory` | **receptor de inventarios** | **el agente (este manual)** |
| `/ocsapi/v1` | API JSON que consume SysAdmin/Yule | `/yule/configuracion/` en el navegador |
| `/ocsreports/` | panel web de administración | el navegador |

La URL que va en el agente es exactamente esta, sin barra al final y sin ninguna
subruta:

```
http://192.168.1.250:8081/ocsinventory
```

> **Por qué el puerto 8081 y no el 80.** En este host los puertos 80 y 443 ya
> los ocupa el sistema de videovigilancia (Hikvision), así que OCS se publique
> en el `8081`. No cambiar el puerto al copiar estos pasos a otro servidor.

Errores frecuentes de URL: `/ocsreports` (es el panel, no el receptor),
`/ocsapi/v1` (es la API), `http://192.168.1.250:8081` (falta la ruta) y
`http://192.168.1.250:80/ocsinventory` (puerto equivocado en este servidor).

---

## 2. Requisitos previos

- El equipo cliente tiene salida por HTTP al servidor en el puerto **8081**.
- Se cuenta con permisos de **administrador** en el equipo (PowerShell como
  administrador).
- No hay que abrir puertos en el firewall del equipo: el agente **solo inicia**
  conexiones hacia el servidor, nunca escucha.
- Si hay firewall de salida o antivirus corporativo, permitir las conexiones
  salientes de `OCSInventory.exe` y `Download.exe` hacia
  `192.168.1.250:8081`.

Comprobar conectividad **antes** de instalar nada (PowerShell):

```powershell
Test-NetConnection 192.168.1.250 -Port 8081
```

Esperado: `TcpTestSucceeded : True`. Si es `False`, no instalar el agente todavía:
el problema es de red y el agente solo fallaría en silencio.

---

## 3. Descargar el instalador

El propio servidor OCS publica el instalador:

```
http://192.168.1.250:8081/download/OcsInventoryAgent.exe
```

En el equipo cliente, en el navegador, escribir esa dirección y descargar. Se
guarda como `OcsInventoryAgent.exe`.

También sirve el paquete oficial, pero **el repo correcto es `WindowsAgent`**, no
`OCSInventory-Agent` (este último da 404):

- Releases: https://github.com/OCSInventory-NG/WindowsAgent/releases
  (asset `OCS-Windows-Agent-2.11.0.1_x64.zip`)
- Sitio oficial: https://ocsinventory-ng.org → *Downloads*

El instalador publicado por nuestro servidor es la vía recomendada: siempre
corresponde a la versión que valida este servidor.

---

## 4. Instalación interactiva (un equipo, con asistente)

1. Doble clic en `OcsInventoryAgent.exe`.
2. Aceptar la licencia.
3. Seleccionar el tipo de instalación **Network inventory** (el equipo llega al
   servidor por red). La opción *Local inventory* genera un archivo `.ocs` para
   importar a mano y no es lo que queremos.
4. En **OCS Inventory NG Communication server URL** escribir exactamente:

   ```
   http://192.168.1.250:8081/ocsinventory
   ```

5. Proxy: **dejar vacío**. Este servidor no usa proxy.
6. Autenticación: **dejar vacía**. El receptor `/ocsinventory` de este servidor no
   pide usuario ni contraseña. Solo se llenan si el servidor exige Basic Auth.
7. SSL: **no usar** (este servidor es HTTP simple). Si algún día se habilita
   HTTPS, el CN del certificado debe ser igual a la dirección que usan los
   agentes.
8. Opcionales recomendados:
   - **Verbose log**: activado, deja traza en `ocsinventory.log` para diagnosticar.
   - **Launch inventory just at the end of setup**: activado, así el equipo
     aparece en el panel sin esperar al temporizador del servicio.
   - **Disable TAG question**: activado, para que no abra un cuadro de diálogo
     pidiendo la etiqueta al usuario.
   - **Register service using LocalSystem account**: **activado**.
9. Carpeta de destino: la por defecto, `C:\Program Files\OCS Inventory Agent`.
10. *Install* → *Finish*.

**No hace falta reiniciar el equipo.** El servicio `OCS Inventory Service` queda
iniciado y el agente reporta por su cuenta.

---

## 5. Instalación silenciosa (despliegue masivo)

Mismo instalador, con parámetros. En PowerShell como administrador, sobre el
ejecutable descargado:

```powershell
.\OcsInventoryAgent.exe /S /NOSPLASH /NOW /NOTAG /SERVER=http://192.168.1.250:8081/ocsinventory
```

| Parámetro | Efecto |
|---|---|
| `/S` | Instalación silenciosa, sin interacción |
| `/NOSPLASH` | Quita la pantalla de inicio |
| `/NOW` | Lanza el inventario al terminar la instalación |
| `/NOTAG` | No pregunta la etiqueta al usuario |
| `/SERVER=` | URL del receptor (aquí es donde va `/ocsinventory`) |
| `/DEBUG=` | Log verboso, para instalar en modo diagnóstico |
| `/NO_SERVICE` | No registrar el servicio (solo agente independiente) |
| `/NO_SYSTRAY` | No crear el icono en el menú Inicio |
| `/NOSOFTWARE` | No inventariar el software instalado |
| `/D=` | Carpeta de instalación distinta |
| `/USER=` `/PWD=` | Credenciales, solo si el servidor exige autenticación |

### Por GPO o con PsExec

`\\servidor\NetLogon\OCS-NG-Windows-Agent-Setup.exe` debe estar en un recurso
compartido. Con **PsExec** (PsTools de Microsoft), a todos los equipos encendidos:

```
psexec \\* -s \\Server\NetLogon\OCS-NG-Windows-Agent-Setup.exe /S /NOSPLASH /NOW /NOTAG /SERVER=http://192.168.1.250:8081/ocsinventory
```

Con credenciales de administrador de dominio:

```
psexec \\* -s -u DOMINIO\Administrador -p CONTRASENA \\Server\NetLogon\OCS-NG-Windows-Agent-Setup.exe /S /NOSPLASH /NOW /NOTAG /SERVER=http://192.168.1.250:8081/ocsinventory
```

A una lista de equipos guardada en `ALL.TXT` (un nombre por línea):

```
psexec @ALL.TXT -s -u DOMINIO\Administrador -p CONTRASENA \\Server\NetLogon\OCS-NG-Windows-Agent-Setup.exe /S /NOSPLASH /NOW /NOTAG /SERVER=http://192.168.1.250:8081/ocsinventory
```

Para los equipos que estén apagados en el momento del despliegue: un script de
inicio de sesión o una GPO que ejecute el mismo instalador, que es idempotente
(si ya está instalado, no rompe nada).

---

## 6. Verificar que el equipo quedó reportando

### 6.1 En el servidor (lo primero, siempre)

```bash
docker logs --tail 40 ocsinventory-server 2>&1 | grep "POST /ocsinventory"
```

Esperado: una línea por equipo con la IP y el `User-Agent` del agente, por
ejemplo `... 2.11.0.1 ...`. **Si no aparece esa línea, el agente no reporta**,
por más que el servicio esté "en ejecución" en el equipo cliente. Ese es el
punto de control que habría detectado el problema original de inmediato.

> Los logs de Apache/OCS se leen con `docker logs ocsinventory-server`. Dentro
> del contenedor `/var/log/apache2/error.log` es un symlink a `/proc/self/fd/2`
> y siempre sale vacío.

### 6.2 En el panel web

```
http://192.168.1.250:8081/ocsreports/
```

El equipo debe aparecer en la lista. Verificar que tenga secciones pobladas
(Resumen → hardware, software, redes). Un equipo con el hardware vacío significa
que el XML llegó incompleto: revisar la sección 8.

### 6.3 En la base de datos de OCS

```bash
docker exec ocsinventory-db sh -c 'mysql -u"$OCS_DB_USER" -p"$OCS_DB_PASS" ocsweb -e "SELECT h.ID, h.NAME, h.LASTCOME, (SELECT COUNT(*) FROM bios b WHERE b.HARDWARE_ID=h.ID) AS bios, (SELECT COUNT(*) FROM networks n WHERE n.HARDWARE_ID=h.ID) AS redes, (SELECT COUNT(*) FROM software s WHERE s.HARDWARE_ID=h.ID) AS software FROM hardware h ORDER BY h.LASTCOME DESC;"'
```

Esperado: una fila por equipo con `LASTCOME` reciente y contadores mayores que
cero.

### 6.4 En SysAdmin / Yule

```bash
docker exec sysadmin_django python manage.py sync_ocs --force
```

Después, en `https://192.168.1.250:6060/yule/`, el equipo debe aparecer con
nombre, sistema operativo, serial, procesador, RAM, IP y MAC.

---

## 7. Configuración avanzada: el archivo `ocsinventory.ini`

El agente guarda toda su configuración en:

```
C:\ProgramData\OCS Inventory NG\Agent\ocsinventory.ini
```

Ahí viven la URL del servidor, las credenciales, el proxy y los tiempos del
servicio. Contenido típico:

```ini
[OCS Inventory Agent]
Debug=1
NoTAG=1
WMI_FLAG_MODE=COMPLETE

[HTTP]
Server=http://192.168.1.250:8081/ocsinventory
SSL=0
AuthRequired=0
User=
Pwd=
ProxyType=0

[OCS Inventory Service]
TTO_WAIT=1020
PROLOG_FREQ=5
```

**Para editarlo hay que detener el servicio antes**, porque con el servicio en
marcha los archivos están protegidos contra escritura:

```powershell
Stop-Service "OCS Inventory Service"
notepad "C:\ProgramData%\OCS Inventory NG\Agent\ocsinventory.ini"
# ... editar Server= si hace falta ...
Start-Service "OCS Inventory Service"
```

Otros archivos del mismo directorio que conviene conocer:

| Archivo | Contenido |
|---|---|
| `ocsinventory.ini` | Configuración del agente y del servicio |
| `ocsinventory.dat` | Identidad única del equipo (basada en MAC y hostname) |
| `ocsinventory.log` | Log verboso, si `Debug=1` o se instaló con `/DEBUG` |
| `last_state` | Estado del último inventario, para detectar cambios |
| `history` | Historial de despliegues de paquetes |

**No borrar `ocsinventory.dat`**: es la identidad del equipo. Si se borra, el
agente genera un `DEVICEID` nuevo y el equipo aparece **duplicado** en el panel.

---

## 8. Cuándo reporta el agente (y por qué a veces parece que no)

Esto genera la mayoría de las dudas después de instalar:

- **La primera ejecución manda el inventario sí o sí.** Si se instaló con
  `/NOW` o con *Launch inventory just at the end of setup*, el equipo aparece de
  inmediato.
- **Después, manda inventario cada `PROLOG_FREQ` horas** (5 por defecto), no en
  cada arranque. El valor se aleatoriza entre 0 y `PROLOG_FREQ` en cada
  instalación para que todos los equipos no golpeen el servidor a la vez.
- **El servicio es solo un lanzador.** `OCS Inventory Service` arranca
  `OCSInventory.exe` sin parámetros, y el agente usa lo que está en
  `ocsinventory.ini`.
- **El servidor también pone reglas.** En la consola de OCS, la opción general
  *FREQUENCY* (en días) indica cada cuánto se le **pide** un inventario al
  equipo. Aunque el agente ejecute, el servidor puede responder "todavía no".

Forzar un inventario en el momento (PowerShell como administrador):

```powershell
& "C:\Program Files\OCS Inventory Agent\OCSInventory.exe" /force /debug=2
```

`/force` manda el inventario aunque el servidor no lo haya pedido (solo
diagnóstico) y `/debug=2` deja traza completa en `ocsinventory.log`. Para ver la
traza:

```powershell
Get-Content "C:\ProgramData\OCS Inventory NG\Agent\ocsinventory.log" -Tail 40
```

---

## 9. Problemas frecuentes

| Síntoma | Causa | Qué hacer |
|---|---|---|
| El servicio está "en ejecución" pero no llega nada al panel | La URL del agente no es `/ocsinventory` | Corregir `Server=` en `ocsinventory.ini` (sección 7) o reinstalar con `/SERVER=` |
| No hay línea `POST /ocsinventory` en `docker logs` | El agente no llegó a hacer la petición | Revisar red (`Test-NetConnection`) y firewall de salida |
| El equipo reporta pero con todos los campos vacíos | XML incompleto: al importarlo a mano se hizo con la sección `hardware` vacía | Relanzar el inventario con `/force`; no usar XML manual |
| El equipo aparece duplicado en el panel | Se borró `ocsinventory.dat` o se desinstaló con limpieza total | Limpiar la fila duplicada en la consola; evitar `/CLEAN=ALL` |
| El servicio no existe tras desinstalar | Quedó el servicio huérfano registrado | `sc delete "OCS Inventory Service"` como administrador, y borrar la carpeta de instalación |
| `POST /ocsinventory/deploy/label` devuelve 400 | El agente consulta la lista de paquetes; no hay paquetes configurados | Es normal, se puede ignorar |
| La página web de OCS sale en blanco | Se recreó el contenedor y se perdieron los parches de PHP/Perl | `bash patch_ocs_server.sh` en el servidor (sección 10) |
| El agente instala pero no queda como servicio | Se usó `/NO_SERVICE` | Reinstalar sin ese parámetro |

---

## 10. Reinstalar o cambiar la URL de un equipo ya instalado

Orden recomendado, del más simple al más profundo:

1. **Cambiar solo la URL**: detener el servicio, editar
   `%ProgramData%\OCS Inventory NG\Agent\ocsinventory.ini`, cambiar `Server=` y
   volver a iniciar el servicio. No requiere desinstalar.
2. **Reinstalar conservando la identidad**: volver a lanzar el instalador con
   `/S /SERVER=http://192.168.1.250:8081/ocsinventory`. Conserva
   `ocsinventory.dat`, así que no se duplica el equipo.
3. **Reinstalación limpia**: desinstalar con el desinstalador del directorio de
   instalación y elegir **solo configuración**:

   ```
   uninst.exe /S /CLEAN=FILES
   ```

   Con `CLEAN=ALL` se borra todo `%ProgramData%\OCS Inventory NG` y el agente
   genera un `DEVICEID` nuevo: el equipo queda **duplicado** en la consola. Solo
   usar esa opción si el equipo va a cambiar de identidad a propósito.

Caso real: el equipo de prueba `192.168.1.137` quedó con un servicio huérfano y
un `DEVICEID` fantasma en OCS por una desinstalación incompleta, lo que dejó
filas basura. Se resolvió borrando el servicio, la carpeta y la fila fantasma de
OCS, y reinstalando limpio. De ahí la advertencia sobre `uninst.exe`.

---

## 11. Desinstalar

Desde *Configuración* → *Aplicaciones* → *OCS Inventory NG Agent* → desinstalar, o
directamente el desinstalador del directorio de instalación
(`C:\Program Files\OCS Inventory Agent\uninst.exe`):

| Comando | Efecto |
|---|---|
| `uninst.exe` | Asistente, pregunta qué limpiar |
| `uninst.exe /S` | Desinstala sin preguntar, **no borra** los datos de `%ProgramData%` |
| `uninst.exe /S /CLEAN=FILES` | Borra `ocsinventory.ini` y la carpeta de descargas |
| `uninst.exe /S /CLEAN=ALL` | Borra todo `%ProgramData%\OCS Inventory NG` |

Después de desinstalar, comprobar que no quedó el servicio:

```powershell
Get-Service "OCS Inventory Service" -ErrorAction SilentlyContinue
sc query "OCS Inventory Service"
```

Si sigue existiendo, borrarlo manualmente:

```powershell
sc.exe delete "OCS Inventory Service"
```

---

## 12. Checklist de cierre por equipo

- [ ] `Test-NetConnection 192.168.1.250 -Port 8081` devuelve `True`.
- [ ] El servicio `OCS Inventory Service` está **en ejecución**.
- [ ] `docker logs --tail 40 ocsinventory-server | grep "POST /ocsinventory"`
      muestra una línea con la IP del equipo.
- [ ] El equipo aparece en `http://192.168.1.250:8081/ocsreports/` con hardware,
      software y redes poblados.
- [ ] `sync_ocs --force` en SysAdmin lo lista con serial, procesador, IP y MAC.
- [ ] El `DEVICEID` del XML cumple el patrón
      `NOMBRE-AAAA-MM-DD-HH-MM-SS`.

---

## 13. Referencia rápida de parámetros del agente

Parámetros que acepta `OCSInventory.exe` una vez instalado (PowerShell como
administrador). El más usado es `/server=`, que además **sobrescribe** el
`ocsinventory.ini` para esa ejecución:

| Parámetro | Significado |
|---|---|
| `/server=http[s]://host[:puerto]/ocsinventory` | Servidor de comunicación (sobrescribe el `.ini`) |
| `/force` | Envía el inventario aunque el servidor no lo pida (diagnóstico) |
| `/debug=0\|1\|2` | Nivel de log: 0 off, 1 verbose, 2 traza completa |
| `/uid` | Genera un nuevo `DEVICEID` (crea duplicado, evitar) |
| `/work_dir="ruta"` | Carpeta de datos del agente |
| `/notag` / `/tag="valor"` | No preguntar la etiqueta / fijar la etiqueta |
| `/xml="ruta"` | Guarda el inventario como XML sin comprimir |
| `/local="ruta"` | No contacta el servidor: genera un `.ocs` para importar luego |
| `/ssl=0\|1` / `/ca="ruta"` | Validación de certificado HTTPS |
| `/user=` / `/pwd=` | Credenciales de autenticación del servidor |
| `/proxy_type=0\|1\|2\|3` | Sin proxy / HTTP / SOCKS4 / SOCKS5 |
| `/proxy=` `/proxy_port=` `/proxy_user=` `/proxy_pwd=` | Datos del proxy |
| `/wmi_flag_mode=COMPLETE\|READ` | Consultas WMI completas o solo locales |
| `/default_user_domain=dominio` | Dominio por defecto si el equipo no está en dominio |

---

## 14. Referencias

- Wiki oficial del agente Windows 2.x:
  https://github.com/OCSInventory-NG/Wiki/blob/master/english/03.Basic-documentation/Setting-up-the-Windows-Agent-2.x-on-client-computers.md
- Releases del agente: https://github.com/OCSInventory-NG/WindowsAgent/releases
- Documentación del servidor OCS: http://192.168.1.250:8081/ocsreports/
- Contexto del servidor y del receptor: `OCS_INVENTORY_SETUP.md`
- Informe del incidente de inventario: `INFORME_OCS_YULE_2026-09-25.md`
