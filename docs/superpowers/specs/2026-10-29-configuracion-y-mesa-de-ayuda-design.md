# Módulo de Configuración de verdad + Mesa de ayuda

**Fecha:** 2026-10-29 · **Estado:** borrador para aprobación · **Base:** `master` v1.13.1 (723 tests)

> Este documento lo escribí con mi criterio: el usuario pidió arrancar sin ronda de
> preguntas. Todo lo que aquí dice "se decide" es **mi decisión**, no algo que él
> haya aprobado. Lo que sí pidió textualmente está marcado como **(pedido)**.

---

## 1. Intención

### Por qué

El enlace «Configuración» del sidebar apunta a `administracion:lista_auditoria`
(`backend/templates/base.html:112`). Es decir: la portada del módulo de configuración
es el registro de auditoría. Configurar algo exige saber que hay dos botones pequeños
arriba a la derecha de esa pantalla.

Y detrás de esos botones hay poco: datos de la empresa, SMTP, código/versión del acta
y las cuentas. **Todo lo que de verdad define cómo se comporta la aplicación está en
código o en el `.env` del servidor**, es decir, fuera del alcance del usuario:

| Qué | Dónde está hoy | Para cambiarlo hay que |
| --- | --- | --- |
| Quién puede ver y tocar cada módulo | `accounts/permisos.py:19` (`PERMISOS_POR_ROL`, dict literal) | editar código, PR, CI, desplegar |
| Qué módulos existen en el menú | `templates/base.html` (bloques `{% if %}` a mano, y `prestamos` apagado con `{% comment %}`) | editar código y desplegar |
| Minutos de inactividad antes de cerrar sesión | `SESSION_COOKIE_AGE` en `.env` | entrar por SSH y reiniciar el contenedor |
| Intentos fallidos antes de bloquear | `AXES_FAILURE_LIMIT = 5` en `settings/base.py` | editar código y desplegar |
| Horas de bloqueo | `AXES_COOLOFF_TIME = 1` en `settings/base.py` | editar código y desplegar |
| Longitud mínima de contraseña | `AUTH_PASSWORD_VALIDATORS` en `settings/base.py` | editar código y desplegar |
| Espera del formulario público de soporte | `.env` | SSH + reiniciar |
| Cuánto historial se guarda | argumentos del cron `limpiar_historial` | SSH |
| Si el SMTP guardado funciona | — | cerrar una orden y esperar a ver si llega el correo |

El síntoma es ese último: hoy no hay forma de saber si el correo está bien configurado
sin provocar un evento real y esperar. `procesar_cola_email()` deja el error en la tabla
`NotificacionEmail`, que no se ve desde ninguna pantalla.

### Cómo se ve el éxito

Un superadministrador entra a **Configuración**, ve una portada con tarjetas por área,
y desde ahí:

- Cambia el minutero de la sesión, los intentos antes de bloquear y la longitud mínima
  de contraseña, y el cambio aplica **en el siguiente request**, sin reiniciar nada.
- Marca una casilla y el módulo Licencias desaparece del menú de todos; sus URLs
  responden 404. Desmarca y vuelve, con sus datos intactos.
- Abre una matriz de roles × módulos, cambia una celda de «lectura» a «escritura» y
  el técnico lo ve al recargar.
- Escribe un correo de prueba, le da a «Probar envío» y lee en pantalla si llegó o cuál
  fue el error exacto del servidor SMTP.
- Abre Auditoría y ve quién cambió qué en la configuración, con el valor anterior y el
  nuevo — y jamás una contraseña.

---

## 2. Alcance y orden de entrega

Esto son dos proyectos independientes. Se entregan en dos planes y dos despliegues.

| Fase | Qué | Tamaño | Plan |
| --- | --- | --- | --- |
| **A. Módulo de Configuración** | configuración en base de datos, matriz de permisos editable, activar/desactivar módulos, retirar Licencias, probar correo, seguridad y retención configurables | Proyecto (12 tareas) | `docs/superpowers/plans/2026-10-29-modulo-configuracion.md` |
| **B. Mesa de ayuda** | convertir Soporte en mesa de ayuda completa | Proyecto | se escribe cuando A esté aprobada |

**A va primero** y no es una preferencia: B necesita que A exista. Las categorías, los
SLA y las respuestas predefinidas de la mesa de ayuda **son configuración**, y su sitio
natural es la portada que construye A. Hacer B primero significa inventar un segundo
lugar donde se configuran cosas, que es exactamente el problema que A viene a arreglar.

---

## 3. Metas, no metas y anti-metas

### Metas (Fase A)

1. Que la portada de Configuración sea configuración, no auditoría. **(pedido)**
2. Que usuarios, contraseñas, correo y seguridad se configuren desde la pantalla. **(pedido)**
3. Que los módulos se puedan activar y desactivar, **excepto** Inventario, Mantenimiento
   y Contraseñas. **(pedido)**
4. Que Licencias quede inactivo y fuera de la vista. **(pedido)**
5. Que todo cambio de configuración quede auditado con valor anterior y nuevo.
6. Que desactivar un módulo sea **cierre real**, no solo esconder el enlace del menú.

### No metas (Fase A, viables después)

- **Plantillas de correo editables** (asunto y cuerpo de cada aviso). Hoy los textos
  están en `soporte/views.py` y `notificaciones/services.py`. Es una fase propia.
- **Permisos por objeto o por sede.** La matriz es rol × módulo × nivel, como hoy.
- **Autenticación LDAP / Active Directory.** GLPI y Zammad lo tienen; aquí no se pidió.
- **Mover a la base de datos lo que arranca la aplicación.** Ver restricciones.
- **Dos factores.** Es la mejora de seguridad con más valor que no está en este alcance;
  se menciona para que no se olvide, no para hacerla aquí.

### Anti-metas (esto convierte la entrega en un fracaso aunque funcione)

1. **Dejar al usuario fuera de su propia aplicación.** Una configuración que permita
   desactivar `administracion`, o quitarle escritura a `superadmin`, es un candado sin
   llave: para arreglarlo hay que entrar al contenedor. El sistema debe **rechazar** esos
   cambios, no advertirlos.
2. **Un secreto en la auditoría o en un log.** La contraseña SMTP se cifra con Fernet
   (`passwords/crypto.py`); un `RegistroAuditoria` con el valor en claro anula ese cifrado.
3. **Desactivar un módulo borrando datos.** Desactivar es reversible por definición.
4. **Un 500 porque una tabla de configuración está vacía.** Base nueva, caché frío o
   `migrate` a medias no pueden tumbar el login.
5. **Repetir el patrón del `.env`:** si para que un cambio aplique hay que reiniciar el
   contenedor, el cambio no está configurado, está escrito en otro archivo.

---

## 4. Restricciones

**Técnicas, no negociables:**

- Django 5.2.18, `django-axes` 8.3.1, HTMX, Bootstrap 5 vendorizado. **Sin dependencias
  nuevas** — ni `django-constance` ni `django-waffle`. Se evaluaron (§5.1) y se descartaron.
- Sin CDN externos (lo vigila `core.tests.VendorAssetsTests`).
- Español en código, interfaz y commits. Commits sin atribución a Claude.
- `ruff check backend` limpio (E,F,W,B,DJ).
- Todo campo de subida nuevo se registra en `MEDIA_PERMISOS` (`core/views.py:36`); hay un
  test que lo exige. Aplica a los adjuntos de la Fase B.
- Campos de fecha en formularios: `forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")`.
  Sin el `format`, con `es-co` el navegador vacía el campo.
- Una vista con confirmación necesita una prueba que haga `GET` y renderice la plantilla.
- Esto toca permisos y sesión en todas las vistas: **va por PR a `master`** para que corra
  el job `test-postgres`, antes de desplegar.

**Lo que NO se mueve a la base de datos** (y por qué): `SECRET_KEY`, credenciales de
PostgreSQL, `PASSWORDS_ENCRYPTION_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
y los ajustes de HTTPS. Se leen **antes** de que exista una conexión a la base, o la
protegen. `PASSWORDS_ENCRYPTION_KEY` además descifra la propia contraseña SMTP: guardarla
en la tabla que ella cifra es una dependencia circular. Siguen en el `.env`.

---

## 5. Fase A — decisiones de diseño

### 5.1 Dónde vive la configuración

**Decisión: campos con tipo en modelos de `administracion`, no un almacén
clave-valor, y sin librería externa.**

Se consideró `django-constance`, que es la respuesta habitual en Django para
«settings editables por el administrador». Se descarta por tres razones concretas:

1. Su interfaz es el `/admin/` de Django, y aquí el `/admin/` está deliberadamente
   reducido (la auditoría es de solo lectura; hay un pendiente abierto de restringirlo
   más). La configuración tiene que vivir en la interfaz propia.
2. Guarda valores sin tipo y validados a mano. Con campos de modelo se obtienen gratis
   la validación, las migraciones y el patrón de `ModelForm` que ya usa todo el repo.
3. `ConfiguracionSistema` ya existe, es un singleton y ya cifra la contraseña SMTP con
   Fernet. Constance sería un segundo lugar donde buscar la configuración.

Lo que GLPI hace es exactamente esto: una tabla de configuración con columnas con nombre
por área, y la interfaz dividida en pestañas (General, Valores por defecto, Activos,
Asistencia, Purga de registros, Seguridad, Rendimiento, API).

`ConfiguracionSistema` crece con grupos de campos nuevos — `sesion_minutos`,
`intentos_antes_de_bloquear`, `horas_de_bloqueo`, `longitud_minima_password`,
`correo_remitente`, `retencion_*` — y los conceptos que son listas se vuelven tablas
propias (`Modulo`, `Rol`, `PermisoRol`).

### 5.2 Cómo aplica sin reiniciar

Tres settings se leen una sola vez al arrancar el proceso. Cada uno tiene su salida:

| Setting | Problema | Solución |
| --- | --- | --- |
| `SESSION_COOKIE_AGE` | se lee al crear la cookie | middleware que hace `request.session.set_expiry(n)` en cada request. Con `SESSION_SAVE_EVERY_REQUEST=True` (ya activo) el minutero de inactividad real sale de ahí |
| `AXES_FAILURE_LIMIT` | se lee en el login | **axes acepta un callable.** `axes/helpers.py:447-455`: si el setting es llamable o una ruta con puntos, lo invoca con `(request, credentials)` y espera un `int` |
| `AXES_COOLOFF_TIME` | ídem | **también acepta callable.** `axes/helpers.py:52-77`: lo invoca con `(request)` y espera un `timedelta` |

La longitud mínima de contraseña **no** se resuelve mutando `AUTH_PASSWORD_VALIDATORS`:
se escribe un validador propio que lee la configuración al validar. Es la única forma
limpia, porque Django instancia los validadores por llamada.

*Nota al margen:* `axes/admin.py:45` comprueba `isinstance(settings.AXES_FAILURE_LIMIT, int)`
para decidir si muestra una columna de estado. Con un callable esa columna desaparece del
`/admin/` de axes. No es un error y no rompe nada; queda dicho para que no se investigue
como un bug.

**Caché.** Cada request leería la configuración varias veces (el menú pregunta por
9 módulos). Se cachea en el backend de caché del proyecto (`FileBasedCache` en
producción, compartido entre workers de gunicorn) y se invalida con un `post_save`.
La caché es un acelerador, no una fuente: si está vacía, se lee de la base.

### 5.3 Matriz de permisos editable

Hoy `PERMISOS_POR_ROL` es un dict literal con 4 roles fijos. Lo bueno es que solo se
lee en **cuatro** sitios de producción, lo que lo hace un cambio contenido:

- `accounts/permisos.py:68` (`tiene_permiso`) y `:89` (`requiere_permiso`)
- `accounts/templatetags/permisos_extras.py:14` (`{% tiene_permiso %}`)
- `core/views.py:65` (`media_protegido`, el que protege los archivos subidos)
- `notificaciones/services.py:28` (`_puede_ver`)

**Decisión:** dos modelos nuevos y un resolvedor único.

- `Rol(clave, nombre, es_sistema, orden)` — los 4 de hoy se siembran con
  `es_sistema=True` y no se pueden borrar. Crear un rol nuevo es insertar una fila, sin
  migración.
- `PermisoRol(rol, modulo, nivel)` con `unique_together`.
- `accounts.permisos.nivel_permiso(rol, modulo) -> "ninguno"|"lectura"|"escritura"`,
  cacheado, **único** punto de lectura. Los cuatro sitios de arriba pasan por él.

**`CustomUser.rol` sigue siendo `CharField`.** Convertirlo a `ForeignKey` obligaría a
migrar las cuentas y a tocar formularios, tests y la sincronización de
`is_superuser`/`is_staff`. En su lugar sus `choices` se vuelven un callable que lee la
tabla `Rol` — Django 5.2 lo admite. Así hay roles nuevos sin cambiar el tipo del campo.

Tres reglas que el resolvedor aplica siempre, por encima de la tabla:

1. `superadmin` tiene `escritura` en todo, siempre. No es editable. Es la llave de repuesto.
2. Un `rol` que no está en la tabla devuelve `ninguno`, no revienta.
3. Tabla vacía (base nueva, migración a medias) → se usa el `PERMISOS_POR_ROL` del código
   como respaldo. Nadie se queda afuera por una tabla sin sembrar.

### 5.4 Activar y desactivar módulos

**El usuario preguntó si es viable: sí, y hay precedente en el propio repo.** `prestamos`
ya está apagado a mano con `{% comment %}` en `base.html:81-88`, y `yule` ya tiene su
propia casilla `integracion_activa`. Lo que falta es que sea datos en vez de HTML comentado.

- Modelo `Modulo(clave, nombre, icono, orden, activo, es_esencial)`, sembrado con los 10
  de `accounts.permisos.MODULOS`.
- `es_esencial=True` para **inventario, mantenimiento, passwords** —los tres que el
  usuario excluyó— **y administracion**, que se añade por la anti-meta 1: sin ella se
  puede cerrar la puerta por dentro. La casilla sale deshabilitada en la pantalla *y*
  el servicio rechaza el cambio; una validación solo en el HTML no es una validación.
- Se siembran **inactivos**: `licencias` **(pedido)** y `prestamos` (ya lo estaba).

**Desactivar cierra en tres capas, porque esconder el enlace no es cerrar:**

1. **`ModuloActivoMiddleware`** → `Http404` si el `app_name` de la URL resuelta pertenece
   a un módulo inactivo. 404 y no una redirección con mensaje: una redirección que dice
   «no tienes permiso» confirma que la sección existe. Nunca se filtran `admin`,
   `accounts`, `core` ni `notificaciones`, o el 404 se lleva por delante el login.
2. **`nivel_permiso`** devuelve `ninguno` para un módulo inactivo → desaparece del menú y
   del tablero, y `@requiere_permiso` corta, sin tocar ninguna vista.
3. **Los avisos** (`notificaciones/services.py`) ya pasan por `_puede_ver`, así que al
   cambiar el resolvedor dejan de generarse solos. `_detectar_licencias` se apaga sin
   tocarlo.

El `app_name` no siempre es la clave del módulo: `reports` → `reportes`, `yule` →
`inventario`. Hace falta un mapa explícito `APP_A_MODULO`.

**Los datos no se tocan.** Desactivar Licencias deja sus filas donde están.

### 5.5 Retirar Licencias

**Decisión: desactivarlo con el mecanismo de §5.4, no borrar el código.**

El usuario dijo «creo que no lo voy a usar». Ese «creo» es la razón de no borrar: con
el interruptor, volver atrás es una casilla; borrando el app, volver atrás es recuperar
código y datos. Además `licencias` tiene cinco puntos de contacto fuera de su carpeta
(menú, matriz de permisos, `notificaciones/services.py::_detectar_licencias`,
la lista de humo de `core/tests.py:445`, `urls.py`) y borrarlos es una cirugía que no
compra nada que la casilla no dé.

Lo único que sí hay que cambiar: la lista de humo de `core/tests.py` abre las URLs de
todos los módulos y daría 404 al desactivar Licencias. Pasa a recorrer solo módulos
activos, y se añade una prueba nueva con el caso contrario (módulo inactivo → 404).

### 5.6 Correo

- **Probar envío**: `administracion:probar_correo`, POST con una dirección. Abre la
  conexión con la configuración **guardada** (`notificaciones.services._get_smtp_connection`,
  que ya existe y es el único sitio que la arma), manda un mensaje y muestra el resultado
  o el error textual del servidor. Con `timeout`, para que un host inalcanzable no cuelgue
  el worker de gunicorn.
- **Remitente** (`correo_remitente`): hoy los correos salen con el `smtp_usuario`. Se
  separa, porque Microsoft 365 permite autenticarse con una cuenta y enviar con otra.
- **Ver la cola**: `NotificacionEmail` tiene `enviado`, `intentos` y `error` y nadie los
  mira. Una tarjeta con lo pendiente y lo fallido, y el botón de reintentar.
- El formulario nunca borra la contraseña guardada si se envía vacío (ya funciona así,
  `forms.py:74`); se añade la prueba que lo fija, porque es lo que se rompe al refactorizar.

### 5.7 Seguridad

Pasan a la configuración, con mínimos que impiden el autobloqueo:

| Campo | Hoy | Mínimo |
| --- | --- | --- |
| `sesion_minutos` | 30 (`.env`) | ≥ 1 — un 0 cierra la sesión en el mismo request en que se guarda |
| `intentos_antes_de_bloquear` | 5 | ≥ 1 |
| `horas_de_bloqueo` | 1 | ≥ 0 (0 = sin bloqueo temporal) |
| `longitud_minima_password` | 10 | ≥ 8 |
| `cooldown_reporte_publico_segundos` | 60 (`.env`) | ≥ 0 |

Se queda en el `.env`, porque nginx también lo aplica y nginx es la autoridad: el
`limit_req` de la ruta pública. La casilla de la aplicación es la segunda barrera, no
la única.

### 5.8 Retención de datos

`limpiar_historial --dias 365 --media-dias 30` ya existe y corre por cron semanal. Sus
números pasan a la configuración (`retencion_dias`, `retencion_media_dias`) y el comando
los lee de ahí cuando no se le pasan argumentos — los argumentos siguen ganando, para no
romper el cron instalado. Y un botón que lo corre en seco (`--dry-run`) y muestra qué
borraría, que es lo que uno quiere antes de confiar en un borrado.

### 5.9 Las pantallas

**Portada** (`administracion:inicio`, a donde apunta el sidebar). Rejilla de tarjetas,
cada una con su descripción y el dato que importa. Es la forma del módulo Configuración
de GLPI y del panel de administración de Zammad: una rejilla por áreas, no un menú.

| Tarjeta | Qué lleva |
| --- | --- |
| Empresa y documentos | nombre, NIT, dirección, teléfono, correo, firma, código y versión del acta |
| Cuentas | las existentes (crear, editar, activar, resetear contraseña) · «N activas de M» |
| Roles y permisos | matriz rol × módulo |
| Módulos | interruptores · «N de M activos» |
| Correo | SMTP, remitente, probar envío, cola · «N pendientes, N con error» |
| Seguridad | sesión, bloqueo, longitud de contraseña |
| Integraciones | OCS/Yule (enlace a `yule:configuracion`, que ya existe) |
| Datos e historial | retención y simulación de limpieza. **Los respaldos no entran:** el pendiente del NAS es que las carpetas no están creadas, y eso no se arregla con una pantalla |
| Auditoría | la pantalla de hoy, ahora una tarjeta entre otras |

**Matriz de permisos**: tabla con los módulos en filas y los roles en columnas, un
`<select>` de tres valores por celda, guardado con HTMX celda a celda. La columna de
`superadmin` se dibuja fija y en gris: no se edita (regla 1 de §5.3), y verla
deshabilitada explica por qué mejor que un mensaje de error al intentarlo.

**Módulos**: una fila por módulo con su interruptor. Los esenciales salen con el
interruptor deshabilitado y la razón escrita al lado, no escondidos.

### 5.10 Auditoría de los cambios

Un ayudante que, dado un `ModelForm` guardado, recorre `form.changed_data` y escribe un
`RegistroAuditoria` con `anterior → nuevo` por campo.

**Los campos de secreto se declaran en una lista y se registran como `(cambiada)`**, sin
el valor ni el anterior. Esto es la anti-meta 2 y es la razón de que el ayudante exista:
si cada vista arma su propio texto de auditoría, tarde o temprano una concatena un valor
que no debía. Hay una prueba que guarda una contraseña SMTP y afirma que no aparece en
ningún `RegistroAuditoria`.

---

## 6. Fase B — mesa de ayuda

Solo el alcance; el plan se escribe aparte. **(pedido: «apoyate en otras opciones de
código abierto»)** — la referencia es GLPI, que es la que se parece a esto: inventario de
activos y mesa de ayuda en la misma aplicación, con los tickets colgando de los activos.
De Zammad y osTicket se toman las piezas de conversación y de base de conocimiento.

Lo que Soporte ya tiene (1270 líneas): formulario público sin login con espera por IP,
estados, prioridad, asignación, escalamiento a una orden de mantenimiento, correo al
solicitante al cambiar de estado, exportación a Excel.

Lo que le falta para ser una mesa de ayuda, en el orden en que da valor:

1. **Hilo de seguimientos** (`SeguimientoTicket`). Es lo primero y lo que más falta:
   hoy un ticket no tiene conversación. GLPI separa tres cosas y la distinción vale
   copiarla: *seguimiento* (comunicación con el solicitante, no cambia el estado),
   *tarea* (trabajo con fecha planificada y duración) y *solución* (lo que cierra).
   Con marca de público o interno: la nota interna es la mitad del valor.
2. **Categorías** (`CategoriaTicket`, árbol) con responsable por defecto. Sin categorías
   no hay forma de saber en qué se gasta el tiempo.
3. **Estados ITIL**: nuevo, en curso (asignado), en curso (planificado), pendiente,
   resuelto, cerrado. Los 5 de hoy se migran. La distinción resuelto/cerrado es la que
   permite el cierre automático del punto 6.
4. **SLA**: tiempo de atención (TTO) y tiempo de solución (TTR) por categoría o
   prioridad, con la fecha límite calculada sobre un calendario laboral y el tiempo en
   «pendiente» descontado. En GLPI el tiempo en pendiente corre la fecha límite, y es
   lo correcto: un ticket esperando respuesta del usuario no consume el SLA del técnico.
5. **Adjuntos** en el ticket y en cada seguimiento (registrar el prefijo en
   `MEDIA_PERMISOS`, hay un test que lo exige).
6. **Cierre automático** de los resueltos después de N días sin objeción, por comando y
   cron, como el `closeticket` de GLPI. N configurable, desde la Fase A.
7. **Respuestas predefinidas** (plantillas de seguimiento).
8. **Base de conocimiento** (`ArticuloConocimiento`), con la opción de FAQ pública ligada
   al formulario público que ya existe.
9. **Portal del solicitante**: «mis tickets» para una cuenta que no es de sistemas.
10. **Encuesta de satisfacción** al cerrar.
11. **Tablero**: abiertos por estado, SLA en riesgo, carga por técnico, tiempo medio.

De la Fase A sale configurable: categorías, SLA, calendario laboral, respuestas
predefinidas, días para el cierre automático y los textos de los correos.

**Lo que se descarta de las referencias:** correo entrante que crea tickets
(buzón IMAP: es un servicio más que puede caerse y el formulario público ya cubre la
entrada), y la búsqueda con Elasticsearch de Zammad (pide entre 4 y 8 GB de RAM en un
servidor que ya corre SysAdmin, OCS, Hikvision, PDF ToolOffice y Kyocera).

---

## 7. Qué queda a criterio del constructor

- La maquetación exacta de las tarjetas y de la matriz, dentro del Bootstrap y las clases
  `sa-*` que ya usa el repo.
- Los nombres de las plantillas y la división de `administracion/views.py`, que con esto
  pasa de 180 a unas 500 líneas y conviene partir por área (el repo ya tiene el precedente
  de `inventario/views/<módulo>.py` y `mantenimiento/views/<módulo>.py`).
- Los textos de ayuda de cada campo.
- Si la matriz guarda celda a celda o con un botón; se sugiere celda a celda con HTMX
  porque es el patrón del repo, pero una tabla con un solo guardado es defendible.

---

## 8. Riesgos

| Riesgo | Por qué importa | Mitigación |
| --- | --- | --- |
| **Autobloqueo** | la configuración puede quitarse a sí misma el acceso | `administracion` es esencial; `superadmin` siempre escritura; mínimos en sesión y bloqueo; todo validado en el servicio, no solo en el HTML |
| **Tocar permisos toca las 60+ vistas** | un fallo del resolvedor abre o cierra todo a la vez | `nivel_permiso` como único punto de lectura, con pruebas de los 4 roles × 10 módulos × 2 niveles; va por PR para que corra `test-postgres` |
| **`choices` llamable en `CustomUser.rol`** | si se evalúa durante `migrate` sobre una base sin la tabla `Rol`, revienta | el callable atrapa el error de base y devuelve los 4 de siempre; hay una prueba que lo fija |
| **Caché de configuración desincronizada** | con varios workers de gunicorn, uno podría servir configuración vieja | `FileBasedCache` es compartida entre workers (ya está así por el `cooldown` de soporte); se invalida en `post_save`; la caché nunca es la fuente |
| **El 404 del middleware se come el login** | un filtro mal escrito deja la aplicación inaccesible | lista explícita de apps que nunca se filtran, con prueba de que el login responde con todos los módulos inactivos |
| **La lista de humo** | abre URLs de los 10 módulos y dará 404 | pasa a recorrer solo módulos activos, más una prueba del caso inactivo |

---

## 9. Fuentes

- [GLPI · Configuración general](https://help.glpi-project.org/glpi-12/fr/setup/general/general_configuration) y [navegación por módulos](https://help.glpi-project.org/documentation/readme-1-1/navigation-modules) — la forma de la portada y las pestañas por área.
- [GLPI · Ciclo de vida del ticket](https://help.glpi-project.org/documentation/modules/assistance/tickets/ticketlifecycle) y [gestión de tickets](https://help.glpi-project.org/documentation/modules/assistance/tickets/ticketmanagement) — estados ITIL, seguimientos / tareas / solución.
- [GLPI · Niveles de servicio](https://help.glpi-project.org/documentation/modules/configuration/service_levels) — SLA, TTO/TTR y escalamiento.
- [Comparativa de mesas de ayuda de código abierto](https://dev.to/selfhostingsh/helpdesk-1681) — de dónde sale el descarte de Elasticsearch por memoria.
- [django-constance](https://django-constance.readthedocs.io/en/stable/) — la alternativa que se evaluó y se descartó en §5.1.
- Código: `axes/helpers.py:52-77` y `:447-455` (callables), `axes/admin.py:45` (la columna que se pierde).
