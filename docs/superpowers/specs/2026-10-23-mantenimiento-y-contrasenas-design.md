# Rediseño de Mantenimiento (checklists, programación y acta) + Importación masiva de contraseñas

**Fecha:** 2026-10-23 · **Estado:** borrador para aprobación · **Bocetos aprobados:** carpeta `2026-10-23-bocetos/` (abrir los `.html` en el navegador)

---

## 1. Intención

### Por qué

Hoy el módulo de mantenimiento registra órdenes sueltas y no guía el trabajo:

- Los planes son **por categoría** y tienen una sola "próxima ejecución" para todos los equipos de esa categoría. Cerrar la orden de un portátil mueve la fecha de todos.
- El checklist solo marca hecho / no hecho. El "estado de partes" y las 4 casillas de acciones van por separado.
- El técnico es un texto libre y el PDF de la orden no trae checklist, fotos ni datos del responsable.

El área de sistemas hace un preventivo así: desarma el equipo y revisa pantalla, bisagras y batería; hace limpieza externa e interna, limpieza de puertos y mantenimiento lógico. Un PC de escritorio lleva lo mismo, menos lo propio del portátil. A celulares, teléfonos y demás no se les hace preventivo.

Se quiere:

1. Que cada mantenimiento **siga un checklist estándar por tipo de equipo** y que no se pueda cerrar sin completarlo.
2. Saber **a qué equipo le toca** con una regla simple: al vencer la garantía y luego cada año. Las fechas no son estrictas: se programa cuando se pueda.
3. Un **acta de una sola hoja carta** con logo, datos detallados del activo, checklist, fotos, QR y firmas, que sirva como evidencia firmada.
4. Aparte: **subir contraseñas en bloque desde Excel** a una bóveda, igual que se importan los activos.

### Cómo se ve el éxito

- Abrir Mantenimiento y ver de inmediato qué equipos tocan, programarlos con dos clics y no recibir alarmas por fechas.
- Hacer el mantenimiento desde el portátil o el celular, punto por punto, y cerrarlo solo cuando el checklist esté completo.
- Imprimir un acta de una hoja, firmarla con el usuario del equipo y subirla escaneada.
- Pegar las contraseñas del Excel en la plantilla, subirla, revisar la vista previa y confirmar.

## 2. Alcance y orden de entrega

| Parte | Tamaño | Orden |
|---|---|---|
| **A. Importación de contraseñas** | Cambio pequeño. Se describió y aprobó en el chat. | Primero |
| **B. Rediseño de mantenimiento + acta** | Proyecto | Después, en un solo despliegue a producción |

## 3. Metas, no metas y anti-metas

**Metas:** las de la §1, con el detalle de las Partes A y B.

**No metas (fuera de este trabajo):**
- Firma digital en pantalla. Se evaluó [signature_pad](https://github.com/szimek/signature_pad) (MIT) y se decidió imprimir y firmar a mano, como el acta de asignación.
- Correos al usuario del equipo o a técnicos. El SMTP sigue sin configurar; solo habrá avisos dentro de SysAdmin.
- Cambiar automáticamente el estado del activo (asignado, en mantenimiento…) al iniciar o cerrar.
- Preventivo para celulares, teléfonos, monitores y periféricos.
- Programación por medidores u horas de uso, como en los CMMS industriales.
- Exportar contraseñas con sus secretos.
- Llevar el software de OCS al acta. Sigue en la hoja de vida.

**Anti-metas (sería un fracaso aunque funcione):**
- Que el acta salga en dos hojas, se corte o cambie de tamaño según el contenido.
- Que el sistema regañe por fechas: rojos de "vencido", bloqueos o insistencia.
- Que editar un checklist cambie mantenimientos ya hechos o actas ya firmadas.
- Que el acta muestre datos que cambiaron después del cierre, como un responsable nuevo o un cambio de IP.
- Que una contraseña importada quede en texto plano en el servidor (BD, sesión, logs o archivos temporales) o se vea en la vista previa.
- Que la importación sobrescriba contraseñas existentes.

## 4. Restricciones

- Stack actual: Django 5.2, PostgreSQL, HTMX, Bootstrap 5, WeasyPrint (PDF), openpyxl (Excel) y qrcode. No se agregan servicios de pago. Cualquier dependencia nueva debe ser libre y estar justificada.
- **El repo es público.** Nada de claves, datos personales reales ni detalles sensibles del servidor en código, tests o docs. Los ejemplos usan datos inventados.
- Producción ya tiene datos (ver §B10). El despliegue sigue el procedimiento actual: `git archive` y backup `pg_dump -Fc` antes.
- Se trabaja con TDD. La suite actual (469 tests) sigue en verde y el CI pasa lint, pip-audit y los tests.
- Regla del proyecto: todo `DateInput` de tipo `date` lleva `format="%Y-%m-%d"`.
- Papel **carta** (216 × 279 mm), no A4.
- La interfaz va en español.

---

## Parte A — Importación masiva de contraseñas

Boceto: `2026-10-23-bocetos/importar-contrasenas.html`. Patrón a copiar: `backend/inventario/views/excel.py` (importar activos).

**Decidido por el usuario:**
- La importación es **por bóveda**: un botón "Importar desde Excel" dentro de cada bóveda y todo entra a esa bóveda. Hoy se usa una sola, pero debe funcionar con varias.
- El flujo es el mismo que en activos: descargar la plantilla, pegar, subir el `.xlsx`, ver la vista previa fila por fila (nuevas / ya existen / con error), confirmar y recibir un mensaje con los totales.
- La plantilla `plantilla_importar_contrasenas.xlsx` tiene una hoja "Plantilla Contraseñas" con las columnas **Título\***, Usuario, **Contraseña\***, URL, Notas, Estado y Fecha de expiración, dos filas de ejemplo con datos inventados y una hoja "Instrucciones". El encabezado es azul #0156A6, como las otras plantillas.
- Todas las columnas van en formato Texto (`@`), para que Excel no cambie claves como `00123` o `1/2/24`.
- Los encabezados se reconocen sin importar mayúsculas ni tildes, con alias: "Clave" o "Password" sirven para Contraseña, y así con las demás columnas. La idea es pegar el Excel propio casi tal cual.
- La vista previa **nunca** muestra la contraseña; aparece como `••••••••`.
- "Ya existe" significa mismo título y mismo usuario en esa bóveda. Esas filas se omiten y nunca se sobrescriben.
- Si falta el título o la contraseña, la fila sale con error y no se importa.
- La contraseña se **cifra apenas se lee el archivo**, con `build_fernet()` de `passwords/crypto.py`. La sesión (que va en la BD) y la vista previa guardan solo el texto cifrado, y al confirmar se guarda ese mismo valor en `secreto_encriptado`.
- La importación queda en la bitácora de la bóveda (`AccesoLog`) con el nombre del archivo y los totales, nunca con las claves.
- Al terminar, la pantalla recuerda borrar el Excel del PC y de la papelera.

**Decisiones mías (revisables):**
- La comparación de duplicados ignora mayúsculas y espacios al inicio y al final. También detecta duplicados dentro del mismo archivo: la segunda fila sale como "Repetida en el archivo".
- Si el Estado viene vacío, queda "Activa". Si no es Activa, Expirada o Revocada, la fila sale con error.
- La fecha acepta `dd/mm/aaaa`, `aaaa-mm-dd` o una celda de fecha de Excel. Si no es válida, la fila sale con error.
- Si la URL no trae esquema, se le antepone `https://`. Si aun así no es una URL válida, el texto va a Notas como "Sitio: …" y la URL queda vacía, sin error.
- Celdas numéricas: si Excel guardó la clave como número (`123456` → `123456.0`), se convierte a texto sin el `.0`. Si la guardó como fecha, la fila sale con error y el mensaje pide usar la plantilla con las columnas en Texto.
- La contraseña se guarda tal cual, sin recortar espacios. Solo se descarta si está vacía o tiene únicamente espacios.
- Requiere el permiso `passwords: escritura`. No pide el código de acceso de la bóveda, igual que cuando se crea una credencial a mano. `creado_por` es quien importa.
- Límites: solo `.xlsx`, máximo 1.000 filas y 5 MB.

---

## Parte B — Mantenimiento

Bocetos: `2026-10-23-bocetos/programacion.html` (pantalla principal) y `2026-10-23-bocetos/acta-una-hoja.html` (acta).
Referencia open source: [Atlas CMMS](https://github.com/grashjs/cmms) (GPLv3). La plantilla del checklist va separada de cada ejecución, y cada punto ejecutado guarda su resultado, una nota y fotos. La recurrencia se cuenta desde la fecha de cierre.

### B1. A qué equipos aplica

- **Preventivo con checklist:** los tipos que tienen plantilla de checklist. Hoy son `portatil` y `escritorio`.
- **Correctivo:** todos los tipos, incluidos los personalizados ("Diadema", "Teclado y Mouse", etc.). Nace de una falla reportada, de un ticket escalado o se crea a mano.
- Los activos dados de baja no aparecen en la programación ni se pueden escoger.

### B2. Checklists (plantillas)

- Hay una plantilla por tipo de equipo y se edita desde la app, en la pantalla **Checklists** (permiso escritura): agregar, quitar y reordenar puntos, y cambiar su texto, su sección y si aplica en garantía. *(mi decisión)* Se puede crear plantilla para otros tipos; el tipo que tenga plantilla entra en la programación.
- Cada punto tiene sección, descripción, orden, **"aplica en garantía"** (sí/no) y activo (sí/no).
- Cada plantilla tiene su **frecuencia en meses**, 12 por defecto.
- Contenido inicial, que se carga en la migración:

| Sección | Portátil | Escritorio | ¿Aplica en garantía? |
|---|---|---|---|
| Hardware | Desarme del equipo | Desarme del equipo | No |
| Hardware | Pantalla | — | No |
| Hardware | Bisagras | — | No |
| Hardware | Batería | — | No |
| Limpieza | Limpieza externa | Limpieza externa | **Sí** |
| Limpieza | Limpieza interna | Limpieza interna | No |
| Limpieza | Limpieza de puertos | Limpieza de puertos | No |
| Mantenimiento lógico | Actualizaciones de Windows | igual | **Sí** |
| Mantenimiento lógico | Antivirus | igual | **Sí** |
| Mantenimiento lógico | Archivos temporales | igual | **Sí** |
| Mantenimiento lógico | Estado del disco | igual | **Sí** |
| Mantenimiento lógico | Programas de inicio | igual | **Sí** |

- Al **iniciar** un preventivo se **copian** a la orden los puntos activos de la plantilla del tipo: todos si el equipo está fuera de garantía, y solo los que "aplican en garantía" si está en garantía. Cambiar la plantilla después no toca las órdenes ya iniciadas o cerradas.

### B3. Hacer un mantenimiento

- **Iniciar:** con "Iniciar" en la fila del equipo (pantalla principal) o con "+ Mantenimiento", donde se elige equipo y tipo. Al iniciar se guarda si el equipo estaba **en garantía ese día**, y eso define el checklist y el tipo que aparece en el acta.
- *(mi decisión)* Mientras un equipo tenga un preventivo abierto, no se le puede iniciar otro preventivo. Los correctivos sí pueden convivir con un preventivo abierto.
- Los estados de la orden siguen siendo los de hoy: reportada, abierta, en proceso, cerrada y cancelada. Un preventivo iniciado queda "en proceso". Se puede cancelar o eliminar como hoy.
- **Checklist:** cada punto se marca con uno de tres botones: **Bien / Con falla / No aplica**. "Con falla" exige una observación corta. *(mi decisión)* Cada punto se guarda al marcarlo (HTMX), con botones grandes para usarlo cómodo desde el celular.
- **Fotos:** se pueden subir varias, cada una con descripción, desde la cámara del celular o desde archivo. *(mi decisión)* El técnico marca hasta 3 para el acta; si no marca ninguna, van las 3 primeras.
- **Repuestos:** como hoy (nombre, referencia, cantidad y costo). En el acta solo salen nombre y cantidad.
- **Observaciones generales** y **Estado final del equipo**: Operativo, Operativo con observaciones o Fuera de servicio.
- **Cerrar** un preventivo exige que todos los puntos tengan resultado, que cada falla tenga su observación y que haya estado final. Un correctivo exige diagnóstico, solución y estado final. Al cerrar:
  - el técnico es **la cuenta con sesión abierta** que cierra;
  - la fecha de cierre es hoy por defecto y se puede cambiar a una fecha pasada, nunca futura *(mi decisión)*;
  - se congela la foto de los datos del acta (§B7);
  - se borra la fecha programada del equipo (§B4).
- *(mi decisión)* Las cuentas de producción hoy **no tienen nombre completo**. Si la cuenta que cierra no tiene nombre, el formulario de cierre le pide **nombre completo y cargo** una sola vez y los guarda en su cuenta. Para eso la cuenta gana un campo `cargo`. Nombre y cargo también se pueden editar en Administración › Cuentas.
- **Una orden cerrada no se edita.** Se puede "Reabrir" con permiso de escritura, lo que descongela el acta. *(mi decisión)* Si ya había un acta firmada subida, se conserva, marcada "de una versión anterior", hasta que se suba la nueva.

### B4. Programación por equipo

**Cuándo le toca a un equipo (fecha "le toca desde"):**
1. Si tiene un **preventivo completo** cerrado (hecho fuera de garantía), le toca en la fecha de cierre del último más la frecuencia del tipo (12 meses).
2. Si no tiene ninguno, le toca el día que **vence la garantía**: `Activo.fecha_vencimiento_garantia`, que suma la compra, los meses de fábrica y los años extendidos.
3. Si no se puede calcular la garantía (falta la fecha de compra o los meses de garantía), se trata como sin garantía y **le toca desde hoy** *(mi decisión)*.
4. Los mantenimientos hechos en garantía y los correctivos **no mueven** esa fecha.

**Estados en la pantalla.** Cada equipo tiene un solo estado, que se evalúa en este orden:
1. **Programado:** tiene fecha programada, sin importar lo demás.
2. **Le toca:** hoy es igual o posterior a la fecha "le toca desde".
3. **En garantía:** hoy es antes del vencimiento y el equipo no tiene ningún preventivo completo.
4. **Al día:** la fecha "le toca desde" es futura.

Las tarjetas de la pantalla principal cuentan cada equipo una sola vez, según este estado.

**Fechas flexibles:**
- La fecha programada es **por equipo**, opcional, y se pone, cambia o quita cuando se quiera. Puede quedar antes o después de la fecha "le toca desde".
- Se puede programar en cualquier estado, también en garantía.
- Nada sale en rojo: "Le toca desde dd/mm/aaaa" va en ámbar y no bloquea nada.

**Calendario:** muestra los equipos programados y las órdenes, como hoy. Los equipos a los que les toca pero no tienen fecha no salen en el calendario. Desaparecen los eventos de planes.

**Avisos en la campana de SysAdmin**, para quien tenga acceso a mantenimiento e idempotentes como los actuales:
- "A ‹equipo› le toca mantenimiento", una vez por ciclo, cuando el equipo entra en "le toca". Sugerencia de `objetokey`: `mant:toca:<activo>:<fecha>`.
- "Mañana: mantenimiento programado de ‹equipo›", el día anterior a la fecha programada.
- Estos avisos reemplazan los que hoy se basan en planes (`notificaciones/services.py::_detectar_mantenimiento`) y no generan correos.

### B5. Pantalla principal de Mantenimiento (boceto `programacion.html`)

- **Tarjetas:** Le toca, Programados, En garantía y Al día.
- **Pestañas:**
  - **Por hacer:** los que les toca, los programados y, *(mi decisión)*, los que les toca en los próximos 30 días.
  - **En garantía.**
  - **Al día.**
  - **Historial:** todas las órdenes, con los filtros de hoy.
  - **Fallas reportadas:** correctivos en estado reportada o abierta.
- Cada fila muestra el equipo (tipo, marca y modelo, serial, N° interno), el responsable (o "No asignado"), el último mantenimiento con su acta y el estado en una etiqueta.
- **Acciones por fila:** Programar o Cambiar fecha, con un selector de fecha en línea, e Iniciar.
- **Botones:** Calendario, Hoja de vida, Checklists y "+ Mantenimiento".
- En el dashboard, "órdenes atrasadas", que hoy se basa en planes, pasa a "equipos a los que les toca" *(mi decisión)*.

### B6. Correctivos

- Se mantienen el portal "Reportar falla" (cualquier usuario con sesión), el escalamiento desde Soporte (ticket → orden) y la creación a mano.
- No llevan checklist. En su lugar tienen **Diagnóstico** y **Solución / acciones realizadas**, además de fotos, repuestos y estado final.
- Su acta usa la misma hoja; la sección 3 se llama "Diagnóstico y solución".

### B7. Acta (boceto `acta-una-hoja.html`, formato aprobado)

**Siempre una sola hoja carta.** Contenido, de arriba abajo:

1. **Encabezado en tabla:**
   - logo;
   - título "ACTA DE MANTENIMIENTO DE EQUIPOS DE CÓMPUTO", o "…DE EQUIPOS" si el activo no es portátil ni escritorio;
   - Código, Versión y "Página 1 de 1". El código y la versión son campos nuevos de Administración › Configuración; si están vacíos, se muestra "—".
2. **Datos del mantenimiento y del equipo:**
   - Acta N° (el número de la orden con 4 dígitos), fecha de cierre y tipo: Preventivo, Preventivo en garantía o Correctivo.
   - Equipo, nombre, N° interno, marca y modelo, serial, procesador, RAM, disco, S.O., IP y ubicación. Un activo de otro tipo muestra sus campos propios dentro del mismo espacio.
   - Garantía: "Hasta dd/mm/aaaa", "Vencida dd/mm/aaaa" o "Sin dato".
   - "Próximo": solo en preventivos. Es la próxima fecha "le toca desde"; en uno hecho en garantía es el vencimiento de la garantía.
   - Los campos vacíos muestran "—".
   - **QR** a la derecha, que lleva a la **hoja de vida** del equipo en SysAdmin (pide iniciar sesión). Su URL absoluta se arma con `QR_BASE_URL`, igual que las etiquetas.
3. **Responsable del equipo:** nombre, C.C., cargo y área de la **asignación activa al cerrar**. Si no hay, dice **"No asignado"**.
4. **Checklist:** va en **dos columnas**, agrupado por sección, con # / punto / resultado (BIEN, FALLA o N/A en color). El título lleva un resumen: "12 puntos · 11 bien · 1 con falla". **No hay columna de observación.** En un correctivo, esta sección es "Diagnóstico y solución".
5. **Evidencia fotográfica:** hasta 3 fotos con su descripción. Si no hay fotos, la sección no aparece.
6. **Repuestos y estado final:** repuestos como nombre × cantidad, o "Ninguno".
7. **Observaciones:** un cuadro justo antes de las firmas. Primero van las fallas del checklist ("Bisagras (falla): …") y después las observaciones generales.
8. **Firmas** con línea para firmar a mano. Técnico: nombre y cargo de la cuenta que cerró. Usuario: el responsable o "No asignado", con cargo y C.C.
9. **Pie:** "SysAdmin · ‹código› v‹versión› · Acta de mantenimiento N° 0042 · dd/mm/aaaa · Página 1 de 1".

**Que nunca pase de una hoja:**
- *(mi decisión)* Límites de texto:
  - observación por punto: 150 caracteres;
  - observaciones generales: 600;
  - diagnóstico: 600;
  - solución: 600.
- Máximo 3 fotos. Si aun así no cabe, se reduce la letra.
- Debe haber una prueba con el contenido máximo que confirme que el PDF tiene una sola página.

**La foto congelada al cerrar:** al cerrar se guarda (por ejemplo en un JSON) todo lo que imprime el acta y no es parte de la orden: datos del equipo, responsable, técnico, garantía y "próximo". El acta se genera **siempre** desde esa foto, así no cambia aunque después cambien el activo, la asignación o la cuenta. El checklist ya es una copia propia de la orden.

**Generación y firma:**
- "Descargar acta" solo existe en órdenes cerradas y el PDF se genera en el momento a partir de la foto congelada *(mi decisión: no se guarda una copia del PDF)*.
- Para firmar: se imprime, se firma a mano y se usa "Subir acta firmada" en el detalle de la orden (PDF, JPG o PNG, hasta 10 MB).
- *(mi decisión)* La campana avisa de las actas de mantenimiento cerradas sin firmar, igual que con las actas de asignación.

**Órdenes viejas:** la única orden que existe en producción (correctiva y cerrada) queda como "formato anterior": conserva su PDF actual (`orden_pdf.html`) y su "estado de partes" visible en el detalle. El acta nueva solo aplica a órdenes creadas después del cambio.

### B8. Otras pantallas que cambian

- **Hoja de vida (pantalla y PDF):**
  - cada mantenimiento muestra el resumen de su checklist (bien / falla / N/A y las fallas con su nota), el estado final y los enlaces al acta y al acta firmada;
  - el software de OCS se queda como está.
- **Reportes:** el Excel de mantenimiento (`reports`) y los PDF de mantenimientos pierden la columna de plan y ganan "En garantía", "Estado final" y "Técnico".
- **Soporte:** escalar un ticket a orden correctiva sigue igual.
- **Dashboard:** ver §B5.

### B9. Qué se elimina

- **Planes por categoría:** el modelo, las pantallas, las URLs, los avisos y los eventos de calendario.
- **Para órdenes nuevas:** el "estado de partes" por tipo (`PARTES_POR_TIPO`), las 4 casillas de acciones y el texto libre `tecnico_asignado`. Los datos viejos se conservan solo para mostrar el formato anterior.

### B10. Migración (datos reales de producción al 2026-10-23)

| Dato | Cantidad | Qué pasa |
|---|---|---|
| Planes | 1 (escritorio, preventivo), sin órdenes ni checklist | Se elimina |
| Órdenes | 1 correctiva cerrada, con estado de partes | Queda como formato anterior |
| Fotos / repuestos / ítems de checklist | 0 / 0 / 0 | — |
| Portátiles + escritorios activos | 11: 10 en garantía y 1 sin fecha de compra | El que no tiene fecha de compra quedará en "le toca" |
| Plantillas de checklist | — | Se crean las 2 iniciales (§B2) |

Antes del despliegue se hace backup con `pg_dump -Fc`, como siempre.

### B11. Permisos

- **Lectura:** ver todo y descargar actas.
- **Escritura:** iniciar, llenar, cerrar, reabrir, programar, editar checklists y subir actas firmadas.
- **Reportar falla:** cualquier usuario con sesión, como hoy.

---

## 5. Herramientas libres

| Herramienta | Licencia | Uso |
|---|---|---|
| WeasyPrint | BSD | PDF del acta (ya en uso) |
| qrcode | BSD | QR del acta (ya en uso) |
| openpyxl | MIT | Plantilla e importación de contraseñas (ya en uso) |
| Atlas CMMS | GPLv3 | Solo como referencia del modelo de datos; no se copia código |
| signature_pad | MIT | Evaluada para firma en pantalla; no se usa por ahora |

## 6. Qué queda a criterio de quien construye

- Nombres de modelos, campos y URLs, y cómo se parten las migraciones. Por ejemplo, si se reutiliza `ChecklistItem` agregándole sección, resultado y observación, o si se crea un modelo nuevo.
- El diseño exacto de cada pantalla, siguiendo el estilo actual (`sa-card`, Bootstrap e HTMX) y los bocetos.
- Cómo se reduce la letra del acta si el contenido no cabe.
- La lista exacta de alias de encabezados en la importación.
- La estrategia de pruebas, siempre con TDD.

