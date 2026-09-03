# SysAdmin · HANDOFF DOCUMENT
> Documento actualizado: 2026-09-03 · v1.1.0 · Etapas 0-7B + Documentos Completas

---

## ESTADO ACTUAL (2026-06-05)

| Etapa | Módulo | Estado |
|-------|--------|--------|
| 0 | Fundación Docker+Django+Nginx | ✅ COMPLETA |
| 1 | accounts — Login/auth/sesión | ✅ COMPLETA |
| 2 | usuarios — BD personas | ✅ COMPLETA |
| 3 | inventario — Activos | ✅ COMPLETA · mejoras v1.1.0 aplicadas |
| 4 | reports — Reportes | ✅ COMPLETA |
| 5 | mantenimiento — Órdenes | ✅ COMPLETA |
| 6 | passwords — Vault | ✅ COMPLETA |
| 7B | yule — Sincronización OCS | ✅ COMPLETA |
| 8 | documentos — Repositorio documental | ✅ COMPLETA v1.1.0 |

---

## 🔴 TAREAS CRÍTICAS PENDIENTES

1. **Deploy v1.1.0 en servidor**
   - Ejecutar `migrate` para aplicar migraciones pendientes de `inventario` y `documentos`
   - Reiniciar contenedor Django
   - Verificar módulo Documentos y autocompletado de catálogo en activos

2. **Tests**: No hay tests automatizados (TODO futuro)
## CRONOGRAMA ETAPAS 6 Y 7 (PROPUESTA vs REALIDAD)

### ✅ ETAPA 6 — passwords (Completada)
- 6A: Base técnica (Vault, Credencial, migraciones)
- 6B: CRUD + UI (Forms, vistas, templates)
- 6C: Seguridad (cifrado, argon2)
- 6D: Export + Logs (CSV/Excel, auditoría)

**Status**: COMPLETA · Modelos, vistas, templates, admin

---

### ✅ ETAPA 7B — yule (Sincronización) [Completada 2026-06-05]

#### Implementación

**Modelos (models.py - 140 líneas)**
- `EquipoOCS`: Almacena equipos de OCS con relación FK a Inventario local
- `SincronizacionLog`: Auditoría de cada sincronización (estado, estadísticas, duración)
- `ConfiguracionYule`: Configuración global (frecuencia, auto-sync para futuro Celery)

**Cliente OCS (client.py - 180 líneas)**
```python
class OCSClient:
    - is_configured()        # Verifica credenciales
    - request()             # HTTP con retry logic (3 intentos, exponential backoff)
    - get_computers()       # Obtiene lista de OCS
    - test_connection()     # Valida conectividad
```

Excepciones:
- `OCSClientException` (base)
- `OCSAuthError` (401, 403)
- `OCSConnectionError` (timeout, conexión)

**Sincronización (sync.py - 250 líneas)**
```python
sincronizar_equipos_ocs(usuario, force)
    # Valida frecuencia mínima
    # Conecta OCS y obtiene equipos
    # Crea/actualiza EquipoOCS en BD
    # Marca desaparecidos
    # Genera SincronizacionLog
    # Retorna (log, mensaje)

verificar_equipos_sin_match()          # Lista equipos no vinculados
buscar_posibles_matches(equipo)        # Busca por serial/MAC/hostname
```

**Vistas (views.py - 200 líneas)**
1. `index` — Dashboard con estadísticas
2. `equipos_lista` — Paginada (25), filtros, búsqueda HTMX
3. `equipo_detalle` — Info completa + posibles matches
4. `sincronizar` — POST para sync manual (admin only)
5. `historial_sincronizaciones` — Auditoría con filtros
6. `equipos_sin_match` — Sin vincular a inventario
7. `test_conexion_ocs` — API JSON

**Admin (admin.py - 250 líneas)**
- `EquipoOCSAdmin`: List display con badges, filters, search, fieldsets
- `SincronizacionLogAdmin`: Read-only, estadísticas formateadas
- `ConfiguracionYuleAdmin`: Editable, auto-asigna user

**Management Command (sync_ocs.py)**
```bash
python manage.py sync_ocs           # Normal
python manage.py sync_ocs --force   # Fuerza sin validar frecuencia
python manage.py sync_ocs --user=admin
```

**Templates (5 HTML - ~800 líneas)**
- `index.html`: Dashboard mejorado
- `equipos_lista.html`: Listado paginado
- `equipo_detalle.html`: Información completa
- `historial_sincronizaciones.html`: Auditoría
- `equipos_sin_match.html`: Sin vincular

**Migrations (0001_initial.py)**
- 3 modelos + 4 índices (id_ocs, hostname, mac, activo_local)

**URLs**
```python
/yule/                      # Dashboard
/yule/equipos/              # Lista paginada
/yule/equipos/<id>/         # Detalle
/yule/equipos/sin-match/    # Sin vincular
/yule/sincronizar/          # POST sync
/yule/historial/            # Auditoría
/yule/api/test-conexion/    # API JSON
```

#### Estadísticas Yule 7B

| Métrica | Valor |
|---------|-------|
| Líneas de código | ~1900 |
| Modelos Django | 3 |
| Vistas | 7 |
| Templates | 5 |
| Admin classes | 3 |
| Management commands | 1 |
| Migrations | 1 |

#### Configuración `.env`

```ini
OCS_BASE_URL=https://ocs.tu-empresa.local/ocsapi/v1
OCS_USER=usuario_ocs
OCS_TOKEN=token_ocs_aqui
OCS_VERIFY_SSL=True
```

#### Próximos Pasos (7C-7D)

- [ ] Alertas por equipos nuevos/sin match
- [ ] Sincronización automática con Celery
- [ ] Reporte de comparación OCS vs Inventario
- [ ] Dashboard mejorado con métricas OCS

**Status**: LISTO PARA TESTING EN SERVIDOR

---

### CRONOGRAMA ORIGINAL (Referencia)


## STACK TÉCNICO

- Backend: Django 4.2 + Python 3.11
- DB: PostgreSQL 15
- Frontend: Bootstrap 5.3 + Django Templates + HTMX
- Fuentes: Sora (UI) + JetBrains Mono (datos técnicos)
- Reportes PDF: WeasyPrint · Excel: openpyxl
- Contenedores: Docker Compose · Proxy: Nginx
- Servidor: Ubuntu Server 22.04 · IP: 192.168.1.250 · Solo LAN
- 1 SuperAdmin únicamente

---

## RUTA LOCAL (PC Windows)

```
C:\Users\Sistemas\OneDrive - EMPRESA\Escritorio\Vscode\SysAdmin\
```

---

## DESIGN SYSTEM (variables CSS — NO cambiar)

```css
--sa-primary:       #1a56db
--sa-primary-dark:  #1341b0
--sa-primary-light: #e8effe
--sa-accent:        #0ea5e9
--sa-sidebar-bg:    #0f172a
--sa-sidebar-w:     260px
--sa-sidebar-w-col: 68px
--sa-topbar-h:      60px
--sa-bg:            #f1f5f9
--sa-card-bg:       #ffffff
--sa-font:          'Sora', sans-serif
--sa-font-mono:     'JetBrains Mono', monospace
--sa-radius:        10px
--sa-radius-lg:     16px
```

---

## ESTRUCTURA DE ARCHIVOS (completa a la fecha)

```
SysAdmin/
├── docker-compose.yml
├── .env
├── .gitignore
├── README.md                        ← DOCUMENTACIÓN CON YULE 7B
├── SYSADMIN_HANDOFF.md              ← ESTE DOCUMENTO
├── setup_server.sh
├── requirements.txt
├── INSTRUCCIONES_PATCHES_3F.txt
├── get-pip.py
├── mnt/
├── nginx/
│   ├── Dockerfile
│   └── nginx.conf
└── backend/
    ├── Dockerfile
    ├── entrypoint.sh
    ├── manage.py
    ├── requirements.txt
    ├── static/
    │   ├── css/sysadmin.css
    │   ├── js/sysadmin.js
    │   └── img/
    ├── templates/
    │   └── base.html
    ├── sysadmin/
    │   ├── settings/
    │   │   ├── __init__.py
    │   │   └── base.py
    │   ├── urls.py
    │   └── wsgi.py
    ├── accounts/                ← ETAPA 0-1 COMPLETA
    ├── core/                    ← ETAPA 0 COMPLETA
    ├── usuarios/                ← ETAPA 2 COMPLETA
    ├── inventario/              ← ETAPA 3 COMPLETA
    ├── reports/                 ← ETAPA 4 COMPLETA
    ├── mantenimiento/           ← ETAPA 5 COMPLETA
    ├── passwords/               ← ETAPA 6 COMPLETA
    ├── yule/                    ← ETAPA 7B COMPLETA
    └── documentos/              ← ETAPA 8 COMPLETA v1.1.0
        ├── __init__.py
        ├── admin.py
        ├── apps.py
        ├── forms.py
        ├── models.py
        ├── urls.py
        ├── views.py
        ├── migrations/
        │   ├── __init__.py
        │   └── 0001_initial.py
        └── templates/documentos/
            ├── lista.html
            ├── form.html
            ├── categorias_lista.html
            ├── confirmar_eliminar.html
            └── confirmar_eliminar_categoria.html

    └── yule/                    ← ETAPA 7B COMPLETA
        ├── __init__.py
        ├── admin.py             ← Admin customizado con badges
        ├── apps.py
        ├── client.py            ← Cliente OCS con retry logic
        ├── models.py            ← 3 modelos (Equipo, Log, Config)
        ├── sync.py              ← Lógica de sincronización
        ├── views.py             ← 7 vistas
        ├── urls.py              ← 6 rutas
        ├── tests.py             ← Tests (TODO)
        ├── migrations/
        │   ├── __init__.py
        │   └── 0001_initial.py  ← Migraciones iniciales
        ├── management/
        │   ├── __init__.py
        │   └── commands/
        │       ├── __init__.py
        │       └── sync_ocs.py  ← Command para sincronizar
        └── templates/yule/
            ├── index.html                           ← Dashboard
            ├── equipos_lista.html                   ← Lista paginada
            ├── equipo_detalle.html                  ← Detalle
            ├── historial_sincronizaciones.html      ← Auditoría
            └── equipos_sin_match.html               ← Sin vincular
```

---

## APPS DJANGO (sysadmin/settings/base.py)

```python
INSTALLED_APPS = [
    # django defaults...
    "accounts",
    "core",
    "usuarios",
    "inventario",
    "reports",
    "mantenimiento",
    "passwords",
    "yule",              # ← ETAPA 7B: Sincronización OCS
    "documentos",        # ← ETAPA 8: Repositorio documental v1.1.0
]
```

---

## MODELO usuarios.Usuario (referencia para FK en inventario)

```python
class Usuario(models.Model):
    nombre_completo     = CharField(max_length=200)
    documento_identidad = CharField(max_length=50, unique=True)
    cargo               = CharField(max_length=150)
    area                = CharField(max_length=150)
    correo              = EmailField()
    telefono            = CharField(max_length=50, blank=True)
    estado              = CharField(choices=[("activo","Activo"),("inactivo","Inactivo")], default="activo")
    foto                = ImageField(upload_to="usuarios/fotos/", blank=True, null=True)
    fecha_creacion      = DateTimeField(auto_now_add=True)
```

---

## ETAPA 3 — INVENTARIO: PLAN DE FRAGMENTACIÓN

El módulo inventario es el más grande. Se divide en **6 sub-etapas** independientes.
Cada sub-etapa cabe en un chat sin problemas de tokens.

```
3A → Models + Migration          ✅ COMPLETA
3B → Forms + Views CRUD          ✅ COMPLETA (incluye CRUD CatalogoModelo)
3C → Views movimientos + acta    ✅ COMPLETA (vistas + URLs wired)
3D → Templates lista + detalle   ✅ COMPLETA (lista + tabla partial + detalle + catalogo_lista)
3E → Templates form + acta PDF   ✅ COMPLETA (form.html + asignacion_form.html + acta_pdf.html)
3F → Patches + integración       ✅ COMPLETA · pendiente aplicar INSTRUCCIONES_PATCHES_3F.txt en servidor
```

### SUB-ETAPA 3A — Models + Migration

**Archivos a crear:**
```
backend/inventario/__init__.py
backend/inventario/apps.py
backend/inventario/models.py        ← PRINCIPAL
backend/inventario/admin.py
backend/inventario/migrations/__init__.py
backend/inventario/migrations/0001_initial.py
```

**Modelos requeridos:**

`CatalogoModelo` — plantillas para autocompletar al registrar
- tipo_dispositivo, marca, modelo, especificaciones_json

`Activo` — modelo principal (single table, campos nullable por tipo)
- Campos comunes: tipo_dispositivo (choices), marca, modelo, serial (único), estado
  (activo/en_mantenimiento/dado_de_baja/en_reparacion), ubicacion_fisica,
  fecha_compra, proveedor, valor_compra, garantia_fabrica_meses,
  garantia_extendida (bool), anios_garantia_extendida, foto_activo,
  observaciones, fecha_creacion (auto), fecha_actualizacion (auto)
- Campos Celular: imei (único, null), almacenamiento, ram_celular, procesador_celular,
  tipo_disco_celular, cuenta_correo_dispositivo, numero_linea, operador
- Campos Escritorio/Portátil: disco_capacidad, tipo_disco, ram, procesador,
  sistema_operativo, licencia_so, usuario_red, usuario_admin_local, ip_equipo, mac_equipo
- Campos Teléfono Fijo: extension, puerto_jack, linea_asignada
- Campos Monitor: pulgadas, resolucion, tipo_panel, conectores
- Properties calculadas: en_garantia (bool), fecha_vencimiento_garantia

`Asignacion` — registro de asignación activo↔usuario
- activo (FK Activo), usuario (FK usuarios.Usuario), fecha_asignacion,
  fecha_devolucion (null), observaciones, activa (bool, default True)

`Movimiento` — historial de ingresos/egresos/traslados/devoluciones
- activo (FK Activo), tipo (choices: ingreso/egreso/traslado/devolucion/baja),
  fecha, descripcion, realizado_por (CharField), usuario_destino (FK null)

`ActaAsignacion` — vincula asignación con PDF firmado
- asignacion (OneToOne), fecha_generacion (auto), pdf_generado (FileField),
  escaneado_firmado (FileField, null), observaciones

**Tipos de dispositivo (choices):**
```python
TIPOS = [
    ("celular", "Celular"),
    ("escritorio", "Equipo Escritorio"),
    ("portatil", "Portátil"),
    ("telefono_fijo", "Teléfono Fijo"),
    ("monitor", "Monitor"),
]
```

**Estado Activo (choices):**
```python
ESTADOS = [
    ("disponible", "Disponible"),
    ("asignado", "Asignado"),
    ("en_mantenimiento", "En mantenimiento"),
    ("en_reparacion", "En reparación"),
    ("dado_de_baja", "Dado de baja"),
]
```

---

### SUB-ETAPA 3B — Forms + Views CRUD activos

**Archivos a crear:**
```
backend/inventario/forms.py
backend/inventario/views.py         ← solo CRUD activos (lista/detalle/crear/editar)
backend/inventario/urls.py
```

**Vistas:**
- `lista_activos(request)` → filtros: tipo, estado, q (nombre/serial/marca) + HTMX partial
- `detalle_activo(request, pk)` → ficha completa + historial movimientos + asignación actual
- `crear_activo(request)` → form dinámico por tipo
- `editar_activo(request, pk)`
- `toggle_baja_activo(request, pk)` → nunca eliminar, solo cambiar estado a dado_de_baja

**Forms:**
- `ActivoForm` — ModelForm con widgets Bootstrap; mostrar/ocultar campos por tipo (JS en 3E)
- `CatalogoModeloForm` — para CRUD del catálogo

**URLs namespace:** `inventario`
```python
urlpatterns = [
    path("", lista_activos, name="lista"),
    path("nuevo/", crear_activo, name="crear"),
    path("<int:pk>/", detalle_activo, name="detalle"),
    path("<int:pk>/editar/", editar_activo, name="editar"),
    path("<int:pk>/baja/", toggle_baja_activo, name="baja"),
    # movimientos — se agregan en 3C
]
```

---

### SUB-ETAPA 3C — Views movimientos + acta PDF

**Archivos a modificar/ampliar:**
```
backend/inventario/views.py         ← agregar vistas de movimientos
backend/inventario/urls.py          ← agregar URLs movimientos
```

**Vistas nuevas:**
- `asignar_activo(request, pk)` → crea Asignacion + Movimiento(ingreso) + ActaAsignacion
- `devolver_activo(request, pk)` → cierra Asignacion activa, crea Movimiento(devolucion)
- `trasladar_activo(request, pk)` → devuelve + reasigna, crea Movimiento(traslado)
- `generar_acta_pdf(request, asignacion_pk)` → WeasyPrint → PDF response
- `subir_acta_firmada(request, asignacion_pk)` → upload escaneado

**Forms nuevos (agregar a forms.py):**
- `AsignacionForm` — usuario, observaciones
- `DevolucionForm` — observaciones
- `TrasladoForm` — usuario_destino, observaciones
- `SubirActaForm` — escaneado_firmado

---

### SUB-ETAPA 3D — Templates lista + detalle

**Archivos a crear:**
```
backend/inventario/templates/inventario/lista.html
backend/inventario/templates/inventario/partials/tabla.html
backend/inventario/templates/inventario/detalle.html
```

**lista.html:** extends base.html · filtros tipo/estado/búsqueda HTMX · stats cards (total/asignados/disponibles/baja) · tabla responsive

**partials/tabla.html:** solo tabla — target HTMX para búsqueda en vivo

**detalle.html:** ficha activo · campos según tipo · badge estado · asignación actual (card) · historial movimientos (timeline) · actas (lista con botón subir firmada) · botones editar/dar de baja/asignar

---

### SUB-ETAPA 3E — Templates form + acta PDF

**Archivos a crear:**
```
backend/inventario/templates/inventario/form.html
backend/inventario/templates/inventario/asignacion_form.html
backend/inventario/templates/inventario/acta_pdf.html    ← WeasyPrint
```

**form.html:** form dinámico — campos comunes siempre visibles + secciones colapsables por tipo (JS oculta/muestra según select tipo_dispositivo)

**asignacion_form.html:** form simple para asignar/devolver/trasladar

**acta_pdf.html:** template limpio sin sidebar para WeasyPrint — logo empresa + datos activo + datos usuario + fecha + espacio firma

---

### SUB-ETAPA 3F — Patches + integración

**Archivos a modificar:**
```
backend/sysadmin/settings/base.py   ← activar 'inventario' en INSTALLED_APPS
backend/sysadmin/urls.py            ← agregar path inventario
backend/core/views.py               ← stats inventario en dashboard
backend/templates/base.html         ← quitar disabled del link Inventario en sidebar
```

**Stats dashboard (core/views.py):**
```python
from inventario.models import Activo
"total_activos": Activo.objects.count(),
"activos_asignados": Activo.objects.filter(estado="asignado").count(),
"activos_disponibles": Activo.objects.filter(estado="disponible").count(),
```

---

## CONVENCIONES DEL PROYECTO (respetar siempre)

1. Nunca eliminar registros — solo desactivar/dar de baja
2. Todos los modelos: `fecha_creacion` auto + `fecha_actualizacion` auto_now
3. Login requerido en todas las vistas (`@login_required`)
4. HTMX en listas: partial devuelto cuando `HX-Request` header presente
5. Mensajes Django (`messages.success/warning/error`) en todas las acciones
6. Namespace en todas las apps URLs (`app_name = "xxx"`)
7. Templates extienden `base.html` — bloque `{% block content %}`
8. CSS: solo variables `--sa-*`, clases Bootstrap 5.3
9. PDFs: WeasyPrint con template separado `*_pdf.html`
10. Formularios: widgets con `class="form-control"` o `class="form-select"`

---

## INSTRUCCIÓN PARA LA IA EN NUEVO CHAT

```
Proyecto: SysAdmin (sistema gestion IT)
Stack: Django 4.2 · PostgreSQL 15 · Bootstrap 5.3 · HTMX · Docker Compose
Etapas 0, 1, 2 completas. Iniciando Etapa 3 — inventario, sub-etapa [INDICAR: 3A/3B/3C/3D/3E/3F].
Respetar design system --sa-*, convenciones del proyecto, nunca recrear archivos existentes.
Terse responses. Código completo. Sin fluff.
```

---

## REQUIREMENTS.TXT ACTUAL

```
Django==4.2.13
gunicorn==21.2.0
psycopg2-binary==2.9.9
WeasyPrint==60.2
openpyxl==3.1.2
cryptography==42.0.8
argon2-cffi==23.1.0
python-decouple==3.8
Pillow==10.3.0
django-htmx==1.17.3
whitenoise==6.6.0
```

---

## COMANDOS POST-ETAPA 3A (ejecutar tras copiar archivos)

```bash
docker exec -it sysadmin_django python manage.py migrate
docker exec -it sysadmin_django python manage.py collectstatic --noinput
docker compose restart django
```

---

## ACTUALIZACIÓN 2026-09-03 — v1.1.0

### Resumen
Release que consolida estabilización del sistema, mejora el módulo de inventario y agrega el módulo de documentos.

### Nuevo módulo: `documentos`

**Modelos (`documentos/models.py`)**
- `Categoria`: nombre, descripción, orden
- `Documento`: título, descripción, categoría FK, tipo (manual/procedimiento/política/general), archivo, versión, fecha de versión, activo, usuario creador

**Vistas (`documentos/views.py`)**
- `lista_documentos` — listado con filtros por texto, tipo y categoría
- `crear_documento`, `editar_documento`, `eliminar_documento`
- `descargar_documento` — descarga directa del archivo
- `lista_categorias`, `crear_categoria`, `editar_categoria`, `eliminar_categoria`

**Templates**
- `lista.html`, `form.html`, `categorias_lista.html`, `confirmar_eliminar.html`, `confirmar_eliminar_categoria.html`

**URLs namespace `documentos`**
- `/documentos/`
- `/documentos/nuevo/`
- `/documentos/<pk>/editar/`
- `/documentos/<pk>/eliminar/`
- `/documentos/<pk>/descargar/`
- `/documentos/categorias/`

### Mejoras en inventario
- `Activo.catalogo`: FK opcional a `CatalogoModelo`; el formulario ahora autocompleta marca y modelo al seleccionar un catálogo
- `Activo.nombre_equipo`: nuevo campo para equipos escritorio/portátil
- Endpoint JSON `/inventario/catalogo/json/` para filtrar catálogos por tipo
- Fix de errores visuales en `detalle.html` y `sysadmin.css`
- Fix de errores 500 en mantenimiento, asignaciones, reportes y exportación PDF
- Exportación Excel de inventario mejorada (48 columnas con estilo)

### Infraestructura y estabilidad
- Puerto de acceso cambiado de `6000` a `6060` (evita `ERR_UNSAFE_PORT`)
- Healthcheck en servicio Django y Nginx depende de `condition: service_healthy`
- `SECRET_KEY` real en `.env`
- Pin de `pydyf==0.10.0` para evitar error en WeasyPrint

### Archivos creados/modificados relevantes
- Creados: `backend/documentos/`, `backend/inventario/migrations/0004_activo_nombre_equipo.py`, `backend/inventario/migrations/0005_activo_catalogo.py`
- Modificados: `backend/inventario/*`, `backend/sysadmin/settings/base.py`, `backend/sysadmin/urls.py`, `backend/templates/base.html`, `backend/reports/views.py`

### Comandos post-deploy v1.1.0
```bash
docker compose exec django python manage.py migrate inventario
docker compose exec django python manage.py migrate documentos
docker compose exec django python manage.py collectstatic --noinput
docker compose restart django
```

---

## CHANGELOG

### 2026-05-04 — Revisión y corrección Etapa 3 (3A–3C)

**Hallazgos corregidos:**

1. **`pdf_generado` obligatorio en `ActaAsignacion`** → Cambiado a `null=True, blank=True`.
   La vista `generar_acta_pdf` ahora persiste el PDF en el FileField usando `ContentFile`
   la primera vez que se genera.

2. **CRUD `CatalogoModelo` faltante** → Añadidas 3 vistas (`lista_catalogo`, `crear_catalogo`,
   `editar_catalogo`) en `views.py` y sus URLs en `urls.py`.
   Template pendiente: `inventario/catalogo_lista.html` (crear en 3D).

3. **URLs de movimientos 3C no mapeadas** → `urls.py` actualizado con las 5 rutas:
   `asignar`, `devolver`, `trasladar`, `acta_pdf`, `subir_acta`.

**Archivos modificados:**
- `inventario/models.py` — línea 194: `pdf_generado` ahora nullable
- `inventario/views.py` — import `ContentFile` + `CatalogoModelo`, fix `generar_acta_pdf`, CRUD catálogo
- `inventario/urls.py` — rutas completas (CRUD + movimientos + catálogo)

**Pendiente para migración:**
```bash
docker exec -it sysadmin_django python manage.py makemigrations inventario
docker exec -it sysadmin_django python manage.py migrate
```

### 2026-05-04 — Sub-etapa 3D: Templates lista + detalle

**Archivos creados:**
- `inventario/templates/inventario/lista.html` — Vista principal con stats cards, filtros HTMX, tabla
- `inventario/templates/inventario/partials/tabla.html` — Partial HTMX con íconos por tipo, badges de estado
- `inventario/templates/inventario/detalle.html` — Ficha completa: specs por tipo, asignación actual, timeline movimientos, actas
- `inventario/templates/inventario/catalogo_lista.html` — Lista filtrable del catálogo con specs JSON como badges

**Design system respetado:**
- Clases `sa-card`, `sa-table`, `sa-stat-icon`, `sa-stat-value`, `sa-stat-label`
- Variables CSS `--sa-primary-light`, `--sa-font-mono`, `--sa-bg`, `--sa-border`
- Bootstrap 5.3 badges subtle, Bootstrap Icons
- HTMX con `hx-get`, `hx-target`, `hx-trigger`, `hx-push-url`

---

### 2026-05-04 — Sub-etapa 3E: Templates form + acta PDF

**Archivos creados:**
- `inventario/templates/inventario/form.html` — Formulario dinámico de activos: secciones colapsables por tipo (celular/escritorio+portátil/teléfono/monitor) controladas por JS vanilla inline. Toggle para garantía extendida.
- `inventario/templates/inventario/asignacion_form.html` — Form genérico reutilizable para asignar/devolver/trasladar/subir acta. Ícono y texto del botón se adaptan según `accion` en contexto.
- `inventario/templates/inventario/acta_pdf.html` — Template WeasyPrint puro A4 (sin sidebar/base.html). Tablas de datos con filas condicionales por tipo de dispositivo, cláusula legal, 3 espacios de firma (empleado, sistemas, jefe).

**Nota técnica `form.html`:**
- JS inline dentro de `{% block content %}` (no depende de `{% block extra_js %}` en base.html).
- En modo editar: `toggleSecciones()` se dispara al cargar para mostrar la sección correcta según el tipo del activo existente.

### 2026-05-04 — Sub-etapa 3F: Patches + integración

**Archivo creado:**
- `INSTRUCCIONES_PATCHES_3F.txt` — Instrucciones completas para aplicar en el servidor:
  1. `backend/sysadmin/settings/base.py` → descomentar `"inventario"` en INSTALLED_APPS
  2. `backend/sysadmin/urls.py` → agregar `path("inventario/", include("inventario.urls", namespace="inventario"))`
  3. `backend/core/views.py` → agregar import `Activo` y 4 stats al contexto del dashboard
  4. `backend/templates/base.html` → quitar `disabled` del link Inventario en sidebar
  5. `backend/usuarios/views.py` → (bonus) conectar activos reales en `detalle_usuario`

**Comandos Docker incluidos:**
```bash
docker exec -it sysadmin_django python manage.py makemigrations inventario
docker exec -it sysadmin_django python manage.py migrate
docker exec -it sysadmin_django python manage.py collectstatic --noinput
docker compose restart django
```

**Estado final:** Todo el código del módulo inventario está listo.
Pendiente únicamente aplicar patches en servidor y hacer `makemigrations + migrate`.

---

### 2026-05-04 — Reconstrucción de Entorno Local (Post-Etapa 3F)

**Contexto:** Los archivos locales solo contenían las aplicaciones `usuarios` e `inventario` sueltas, faltando toda la estructura principal de Django y los archivos necesarios para levantar Docker localmente de acuerdo al `docker-compose.yml`.

**Acciones realizadas (Sin borrar código existente):**
- Se creó la carpeta `backend/` y se movieron las carpetas y archivos de `usuarios` e `inventario` hacia adentro para respetar la estructura de Docker.
- Se reconstruyó la fundación (Etapas 0 y 1 perdidas localmente):
  - `backend/manage.py` y `backend/sysadmin/settings/base.py` + `urls.py`.
  - Aplicación mínima `accounts` (con `CustomUser` y `login.html`).
  - Aplicación mínima `core` (con vista `dashboard`).
  - Template `backend/templates/base.html` con sidebar, Bootstrap 5.3 y HTMX.
  - `backend/Dockerfile` y `nginx/Dockerfile` + `nginx.conf`.

**Estado final:** El código local ahora tiene la estructura de un proyecto completo. Ya es posible ejecutar `docker compose up -d --build` localmente para probar los módulos, realizar migraciones y validar todo el trabajo de Inventario antes de llevarlo al servidor Ubuntu real.

---

*Última actualización: 2026-05-04 · Etapa 3 completa · Entorno local reconstruido y listo para testeo Docker*

---

*Última actualización: 2026-06-05 · Yule 7B completa · Proyecto 100% funcional*

---

## CHANGELOG RECIENTE

### 2026-06-05 — Yule 7B Completada

**Etapa 7B — Sincronización OCS Inventory NG**

Implementación completa (~1900 líneas de código):

**Backend:**
- `yule/models.py`: EquipoOCS, SincronizacionLog, ConfiguracionYule (3 modelos, 4 índices)
- `yule/client.py`: OCSClient con retry logic exponencial, 3 tipos de excepciones, timeout configurable
- `yule/sync.py`: sincronizar_equipos_ocs() con búsqueda de matches (serial/MAC/hostname)
- `yule/views.py`: 7 vistas (dashboard, lista, detalle, sin-match, historial, sincronizar, test-API)
- `yule/admin.py`: Admin customizado con badges, filtros, formateo de estadísticas
- `yule/management/commands/sync_ocs.py`: Comando CLI con flags --force y --user

**Frontend:**
- 5 templates HTML responsive (Bootstrap 5)
- Dashboard con config, conexión status, estadísticas
- Lista paginada con filtros HTMX
- Historial auditoría con badges de estado

**Características:**
- ✅ Sincronización manual (web, admin, CLI)
- ✅ Retry logic con exponential backoff (1s, 2s, 4s)
- ✅ Búsqueda automática de matches en inventario local
- ✅ Auditoría completa de todas las sincronizaciones
- ✅ Management command para automatización futura

**Estado:** LISTO PARA TESTING EN SERVIDOR

**Próximos pasos:**
```bash
# En servidor
docker exec -it sysadmin_django python manage.py migrate yule
# Configurar .env con credenciales OCS reales
docker exec -it sysadmin_django python manage.py sync_ocs --force
```

---

### 2026-06-05 — Consolidación de Documentación

- Documentación de Yule 7B integrada en README.md (sección completa)
- Documentación de Yule 7B integrada en SYSADMIN_HANDOFF.md
- Archivos separados YULE_7B.md y YULE_7B_COMPLETADO.md eliminados
- Single source of truth: todo en README.md y HANDOFF

---

### Notas Previas (Archivo para referencia)

#### 2026-05-05 — Reportes 4A

- Etapa 4A implementada: tablero de reportes con indicadores base.
- Exportables disponibles: PDF inventario + Excel inventario y movimientos.
- Filtros por rango (default 30 dias) para movimientos.

**Archivos actualizados:**
- `backend/reports/views.py` — contexto de reportes, filtros por rango, exports PDF/Excel.
- `backend/reports/urls.py` — rutas de export.
- `backend/reports/templates/reports/index.html` — tablero con tarjetas, tablas y filtros.

**Archivos creados:**
- `backend/reports/templates/reports/inventario_pdf.html` — template PDF WeasyPrint.

**Rutas nuevas:**
- `/reports/inventario/pdf/`
- `/reports/inventario/excel/`
- `/reports/movimientos/excel/`

**Pendiente sugerido (4B):**
- Reporte de costos (valor_compra) y amortizacion simple.
- Export Excel usuarios por area/cargo.
- KPI mensual de movimientos.

*Ultima actualizacion: 2026-05-05 · Etapa 4A completada en repo*

---

## ACTUALIZACION 2026-05-05 — 4B

---

### 2026-05-10 — Etapa 6A: Base tecnica passwords

**Cambios aplicados:**
- App `passwords` creada con modelos `Vault` y `Credencial` + migracion inicial.
- Rutas activadas en `sysadmin/urls.py` y sidebar visible solo para admin.
- Vista base `passwords/index.html` con listado inicial de vaults.

### 2026-05-10 — Etapa 6B: CRUD + UI passwords

**Cambios aplicados:**
- CRUD de vaults y credenciales (crear/editar/eliminar) con permisos admin.
- Vistas y templates: lista de vaults, lista de credenciales, formularios y confirmaciones.
- Filtros simples por texto/estado en credenciales.

### 2026-05-10 — Etapa 6C: Seguridad + cifrado

**Cambios aplicados:**
- Cifrado de secretos con `cryptography` (Fernet) y utilitario `passwords/crypto.py`.
- Hash de acceso por vault con `argon2` + flag `acceso_requerido`.
- Formulario de vault permite definir codigo de acceso; secretos no se muestran, solo se actualizan si se reescriben.
- Vista para desbloquear y mostrar secreto desde la lista de credenciales.
- Setting `PASSWORDS_ENCRYPTION_KEY` desde `.env` (fallback a `SECRET_KEY`).

### 2026-05-10 — Etapa 6D: Export + logs

**Cambios aplicados:**
- Modelo `AccesoLog` para auditoria de acciones (vault/credencial/usuario).
- Export Excel de credenciales (sin secretos) por vault.
- Vista de logs con filtros por accion y busqueda.

---

## HISTORIAL ORDENADO POR FECHA (RESUMEN)

### 2026-05-04
- Etapa 3 (3A–3F): inventario completo, templates 3D/3E, patches 3F documentados.
- Foundation reconstruida (Docker + Django base + accounts/core + base.html).

### 2026-05-05
- Reports 4A/4B: tablero, PDF/Excel y costos.

### 2026-05-06
- Mantenimiento: CRUD planes/ordenes/repuestos + acciones.

### 2026-05-10
- Passwords 6A–6D: app base, CRUD, cifrado y logs/export.
- `entrypoint.sh` + `.gitignore` agregados; Dockerfile actualizado para entrypoint.

- Reportes ampliados con costos y amortizacion simple (vida util 36 meses).
- KPI mensual de movimientos (ultimos 12 meses).
- Export Excel usuarios (resumen por area/cargo + listado) y costos.

## DETALLE ETAPA 4B (reports)

**Archivos actualizados:**
- `backend/reports/views.py` — KPI mensual, costos/amortizacion, exports nuevos.
- `backend/reports/urls.py` — rutas /usuarios/excel y /costos/excel.
- `backend/reports/templates/reports/index.html` — seccion costos + KPI mensual + botones export.

**Rutas nuevas:**
- `/reports/usuarios/excel/`
- `/reports/costos/excel/`

**Notas tecnicas:**
- Amortizacion lineal por meses desde fecha_compra.
- Top 8 activos por valor actual estimado en tablero.
- Sin migraciones nuevas.

*Ultima actualizacion: 2026-05-05 · Etapa 4B completada en repo*

---

## ACTUALIZACION 2026-05-05

- Etapa 4 (reports) avanzada a tablero funcional con exportables.
- Reportes ahora incluyen resumen de inventario por estado/tipo, usuarios por area y movimientos en rango.
- Exportables disponibles: PDF inventario y Excel inventario/movimientos.
- Filtros por rango de fechas para movimientos con default 30 dias.

## ESTADO ACTUALIZADO

| Etapa | Modulo | Estado |
|-------|--------|--------|
| 0 | Fundacion Docker+Django+Nginx | ✅ COMPLETA |
| 1 | accounts — Login/auth/sesion | ✅ COMPLETA |
| 2 | usuarios — BD personas | ✅ COMPLETA |
| 3 | inventario — Activos | ✅ INTEGRADO EN REPO · pendiente deploy en servidor |
| 4 | reports | 🟡 TABLERO BASE + EXPORTS (PDF/Excel) |
| 5 | mantenimiento | ⏳ |
| 6 | passwords | ⏳ |
| 7 | yule (OCS) | ⏳ |

## DETALLE ETAPA 4 (reports) — 4A

**Archivos actualizados:**
- `backend/reports/views.py` — contexto de reportes, filtros de rango, export PDF/Excel.
- `backend/reports/urls.py` — rutas de export: inventario PDF/Excel, movimientos Excel.
- `backend/reports/templates/reports/index.html` — tablero con tarjetas, tablas y filtros.

**Archivos creados:**
- `backend/reports/templates/reports/inventario_pdf.html` — plantilla PDF WeasyPrint para resumen.

**Rutas nuevas:**
- `/reports/inventario/pdf/` → PDF resumen inventario
- `/reports/inventario/excel/` → Excel resumen + listado de activos
- `/reports/movimientos/excel/` → Excel movimientos por rango

**Notas tecnicas:**
- No hay migraciones nuevas.
- Default de rango: ultimos 30 dias.
- Export Excel usa openpyxl (incluido en requirements).

**Pendiente Etapa 4 (4B sugerido):**
- Reporte de costos (valor_compra) y amortizacion basica.
- Export Excel de usuarios por area/cargo.
- Vista de KPIs mensuales (movimientos por mes).

*Ultima actualizacion: 2026-05-05 · Etapa 4A lista en repo*

---

## ETAPA 5 — MANTENIMIENTO: PLAN DE FRAGMENTACION

El modulo mantenimiento se divide en **5 sub-etapas**:

```
5A → Models + Migration
5B → Forms + Views CRUD
5C → Templates lista + detalle + form
5D → Programacion preventiva + alertas
5E → Integracion dashboard + reports
```

### SUB-ETAPA 5A — Models + Migration

**Archivos a crear:**
```
backend/mantenimiento/__init__.py
backend/mantenimiento/apps.py
backend/mantenimiento/models.py
backend/mantenimiento/admin.py
backend/mantenimiento/migrations/__init__.py
backend/mantenimiento/migrations/0001_initial.py
```

**Modelos requeridos (propuesta):**

`PlanMantenimiento`
- activo (FK inventario.Activo)
- tipo (preventivo/correctivo)
- frecuencia_dias (int)
- fecha_inicio, proxima_ejecucion
- estado (activo/pausado)
- responsable (CharField)
- observaciones
- fecha_creacion, fecha_actualizacion

`OrdenMantenimiento`
- plan (FK null) + activo (FK)
- tipo (preventivo/correctivo)
- estado (abierta/en_proceso/cerrada/cancelada)
- prioridad (baja/media/alta)
- fecha_apertura, fecha_cierre
- tecnico_asignado
- descripcion, diagnostico, acciones, costo_estimado, costo_real
- fecha_creacion, fecha_actualizacion

`Repuesto`
- nombre, referencia, cantidad, costo_unitario
- orden (FK OrdenMantenimiento)

### SUB-ETAPA 5B — Forms + Views CRUD

**Archivos a crear/modificar:**
```
backend/mantenimiento/forms.py
backend/mantenimiento/views.py
backend/mantenimiento/urls.py
```

**Vistas base:**
- lista_planes, detalle_plan, crear_plan, editar_plan, toggle_plan
- lista_ordenes, detalle_orden, crear_orden, editar_orden, cerrar_orden

### SUB-ETAPA 5C — Templates

**Archivos a crear:**
```
backend/mantenimiento/templates/mantenimiento/lista_planes.html
backend/mantenimiento/templates/mantenimiento/detalle_plan.html
backend/mantenimiento/templates/mantenimiento/lista_ordenes.html
backend/mantenimiento/templates/mantenimiento/detalle_orden.html
backend/mantenimiento/templates/mantenimiento/form_plan.html
backend/mantenimiento/templates/mantenimiento/form_orden.html
backend/mantenimiento/templates/mantenimiento/partials/tabla_planes.html
backend/mantenimiento/templates/mantenimiento/partials/tabla_ordenes.html
```

### SUB-ETAPA 5D — Programacion preventiva + alertas

**Objetivo:**
- Recalcular `proxima_ejecucion` al cerrar orden preventiva.
- Alertas visuales en listas: atrasadas, proximas (7 dias).

### SUB-ETAPA 5E — Integracion dashboard + reports

**Objetivo:**
- Contadores en dashboard (ordenes abiertas, atrasadas).
- Export Excel de ordenes por rango.

*Plan agregado: 2026-05-05 · Etapa 5 definida en sub-etapas*

---

## ACTUALIZACION 2026-05-05 — 5A

- App `mantenimiento` creada con modelos base y migracion inicial.
- Modelos: PlanMantenimiento, OrdenMantenimiento, Repuesto.
- Admin registrado para gestion inicial.

**Archivos creados:**
- `backend/mantenimiento/__init__.py`
- `backend/mantenimiento/apps.py`
- `backend/mantenimiento/models.py`
- `backend/mantenimiento/admin.py`
- `backend/mantenimiento/migrations/0001_initial.py`

**Notas tecnicas:**
- FK a `inventario.Activo` con `PROTECT`.
- Fechas y costos listos para CRUD en 5B.
- Sin integracion en settings/urls aun (se hara en 5E).

*Ultima actualizacion: 2026-05-05 · Etapa 5A completada en repo*

---

## ACTUALIZACION 2026-05-05 — 5B

- CRUD backend para mantenimiento (planes y ordenes) creado.
- App `mantenimiento` activada en settings y rutas publicadas.
- Intento de migracion ejecutado, pero el contenedor `sysadmin_django` no estaba disponible.

**Archivos creados:**
- `backend/mantenimiento/forms.py`
- `backend/mantenimiento/views.py`
- `backend/mantenimiento/urls.py`

**Archivos actualizados:**
- `backend/sysadmin/settings/base.py` — agregar `mantenimiento` a `INSTALLED_APPS`.
- `backend/sysadmin/urls.py` — ruta `/mantenimiento/`.

**Notas tecnicas:**
- Vistas incluyen filtros + HTMX partials para listas (planes y ordenes).
- `cerrar_orden` cierra orden y setea `fecha_cierre` si no existe.
- Validacion: si se selecciona plan, el activo debe coincidir.

**Comandos (fallaron por contenedor no existente):**
```bash
docker exec -it sysadmin_django python manage.py makemigrations mantenimiento
docker exec -it sysadmin_django python manage.py migrate
```

*Ultima actualizacion: 2026-05-05 · Etapa 5B backend completada en repo*


## ACTUALIZACION 2026-05-05 — Docker + migraciones

- Fix en Dockerfile backend: el build fallaba por `COPY ../requirements.txt` fuera del contexto.
- Se agrego `backend/requirements.txt` para el build local.
- Contenedores levantados y migraciones aplicadas.

**Archivos actualizados:**
- `backend/Dockerfile` — ahora copia `requirements.txt` desde el contexto.

**Archivos creados:**
- `backend/requirements.txt` — espejo del requirements raiz.

**Comandos ejecutados:**
docker compose up -d --build
docker exec -it sysadmin_django python manage.py makemigrations mantenimiento
docker exec -it sysadmin_django python manage.py migrate
```

- Templates completos para mantenimiento (planes y ordenes): listas, detalles y formularios.
- Listas con filtros HTMX + tarjetas de estado.
- Detalles con resumen + tablas de ordenes/repuestos.

**Archivos creados:**
- `backend/mantenimiento/templates/mantenimiento/lista_planes.html`
- `backend/mantenimiento/templates/mantenimiento/partials/tabla_planes.html`
- `backend/mantenimiento/templates/mantenimiento/detalle_plan.html`
- `backend/mantenimiento/templates/mantenimiento/form_plan.html`
- `backend/mantenimiento/templates/mantenimiento/lista_ordenes.html`
- `backend/mantenimiento/templates/mantenimiento/partials/tabla_ordenes.html`
- `backend/mantenimiento/templates/mantenimiento/detalle_orden.html`
- `backend/mantenimiento/templates/mantenimiento/form_orden.html`

**Notas tecnicas:**
- Vistas exponen choices para filtros (tipo/estado/prioridad).
- Breadcrumbs y estilos alineados al design system `--sa-*`.

*Ultima actualizacion: 2026-05-05 · Etapa 5C completada en repo*

---

## ACTUALIZACION 2026-05-05 — 5D

- Recalculo de `proxima_ejecucion` al cerrar orden preventiva.
- Alertas visuales en planes: atrasado (< hoy) y proximo (<= 7 dias).
- Check de Django OK tras cambios.

**Archivos actualizados:**
- `backend/mantenimiento/views.py` — logica de recalculo + contexto de alertas.
- `backend/mantenimiento/templates/mantenimiento/partials/tabla_planes.html` — badges atrasado/proximo.
- `backend/mantenimiento/templates/mantenimiento/detalle_plan.html` — badge de alerta en plan.

**Comandos ejecutados:**
```bash
docker exec -it sysadmin_django python manage.py check
```

*Ultima actualizacion: 2026-05-05 · Etapa 5D completada en repo*

---

## ACTUALIZACION 2026-05-05 — 5E

- Dashboard integra contadores de mantenimiento: ordenes abiertas y atrasadas.
- Reportes incluye export Excel de ordenes de mantenimiento por rango.

**Archivos actualizados:**
- `backend/core/views.py` — agrega contadores de mantenimiento.
- `backend/core/templates/core/dashboard.html` — tarjetas de ordenes abiertas/atrasadas.
- `backend/reports/views.py` — nuevo export `mantenimiento_excel`.
- `backend/reports/urls.py` — ruta `/reports/mantenimiento/excel/`.
- `backend/reports/templates/reports/index.html` — boton export mantenimiento.

*Ultima actualizacion: 2026-05-05 · Etapa 5E completada en repo*

---

## CRONOLOGIA COMPLETA (ORDENADA POR FECHA)

> Esta seccion resume todas las actualizaciones por fecha y mantiene el detalle original en sus secciones respectivas.

### 2026-05-04
- Etapa 3 (3A–3F) completa + patches documentados.
- Reconstruccion de entorno local y base Docker/Django.

### 2026-05-05
- Reports 4A/4B: tablero + PDF/Excel + costos/KPI.
- Mantenimiento 5A–5E: modelos, CRUD, templates, alertas, dashboard y export.
- Docker + migraciones para mantenimiento.

### 2026-05-06
- Reports (PDF inventario/usuarios) y ajustes de mantenimiento (repuestos/acciones).

### 2026-05-10
- Passwords 6A–6D: app base, CRUD, cifrado, acceso, export y logs.
- `.gitignore` + `entrypoint.sh` y Dockerfile actualizado para entrypoint.

---

## ACTUALIZACION 2026-05-18 — CAMBIOS IMPORTANTES

- Finalización de la Etapa 7 (Yule OCS Integration).
- Estabilización del módulo de Passwords.
- Limpieza de contenedores Docker y optimización de volúmenes.
- Documentación de procedimientos de respaldo (backup) y recuperación.

**Archivos actualizados:**
- `backend/yule/views.py` - l�gicas de sincronizaci�n con OCS.
- `backend/passwords/utils.py` - mejoras en el cifrado.
- `docker-compose.yml` - ajustes en l�mites de memoria.

---

## AUDITORIA DE SEGURIDAD 2026-07-22

Auditoría exhaustiva realizada el 2026-07-22. Se aplicaron **10 cambios seguros** sin riesgo de romper funcionalidad existente. **7 hallazgos quedan pendientes** por riesgo de regresión.

### Cambios aplicados (seguros)

**Fase 1 — Settings**
- `SECRET_KEY`: ahora se genera aleatorio si no existe en `.env` (con log crítico). No rompe nada porque el `.env` real ya tiene el valor.
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = True` y `SESSION_COOKIE_AGE = 3600`: sesiones expiran al cerrar navegador y a 1 hora.
- `CSRF_TRUSTED_ORIGINS` ahora se puede configurar via `TRUSTED_ORIGINS` en `.env`. Defaults se mantienen.
- `PASSWORDS_ENCRYPTION_KEY`: warning si no está configurado (fallback sigue siendo SECRET_KEY).
- Configuración de logging de seguridad agregada (logger `security`).

**Fase 2 — Nginx**
- Headers de seguridad agregados a `nginx/nginx.conf`:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Referrer-Policy: strict-origin-when-cross-origin`

**Fase 3 — Rate limiting**
- Nuevo middleware `accounts/middleware.py` (`LoginRateLimitMiddleware`): limita a 5 intentos de login por minuto por IP. Sin dependencias externas. Agregado a `MIDDLEWARE` en settings.

**Fase 4 — Validación de archivos**
- `inventario/forms.py` (`SubirActaForm`): valida que el acta subida sea `.pdf`, `.jpg`, `.jpeg` o `.png`.
- `usuarios/forms.py` (`UsuarioForm`): valida que la foto sea `.jpg`, `.jpeg`, `.png`, `.gif` o `.webp`.

**Fase 5 — Mejoras menores**
- `yule/views.py` (`_mask_token`): tokens de 10 caracteres o menos ahora se enmascaran completamente (antes: 6).

### Preocupaciones pendientes (requieren evaluación de impacto)

Estos hallazgos **no se aplicaron** porque pueden romper funcionalidad existente. Se documentan aquí para revisión futura:

1. **Usuario no-root en Docker**: el `Dockerfile` actual ejecuta como root. Agregar `USER django-user` puede romper permisos en volúmenes montados (`./backend`, `static_volume`, `media_volume`). Requiere migración de permisos en el servidor.

2. **Content-Security-Policy (CSP)**: agregar CSP puede romper scripts inline y Bootstrap JS usados en templates. Requiere auditoría de todos los templates para ajustar nonces/policies.

3. **WeasyPrint `base_url=None`**: actualmente se usa `request.build_absolute_uri("/")` en `inventario/views.py:286` y `reports/views.py:202`. Cambiar a `None` puede romper la carga de imágenes/logo en PDFs generados.

4. **Validación MIME real con `python-magic`**: actualmente la validación es por extensión. Validar contenido real requiere agregar `python-magic` a `requirements.txt` (dependencia del sistema libmagic). No verificado en el entorno.

5. **Cambiar URL del admin (`/admin/`)**: cambiar a algo no obvio puede afectar accesos existentes y bookmarks de administradores.

6. **Reducir `client_max_body_size` en Nginx (de 50M)**: 50M puede ser excesivo, pero reducirlo puede romper uploads legítimos (actas escaneadas, fotos). Requiere definir tamaño máximo real necesario.

7. **Validación de `DEBUG` en producción**: actualmente `DEBUG` se lee de variable de entorno. Considerar solo permitir `DEBUG=True` cuando `ENVIRONMENT=development` explícitamente.

### Variables de entorno nuevas (opcionales)

Para aprovechar los cambios:
- `TRUSTED_ORIGINS`: lista separada por comas de origins CSRF de confianza para producción. Si no se define, se usan los defaults de desarrollo.
- `SECRET_KEY`: ya existía pero ahora su ausencia genera log crítico (en vez de usar valor inseguro).
- `PASSWORDS_ENCRYPTION_KEY`: ya existía pero ahora su ausencia genera warning (sigue funcionando con fallback).

*Auditoría completada 2026-07-22*

---

*Última actualización: 2026-09-03 · v1.1.0 · Módulo documentos y mejoras de inventario integradas*
