# SysAdmin · Sistema de Gestión IT



            .---''''''''''''''''''''''''''''''''''''''''---.
          .-'     ((((                                         '-.
        .'       ((((   ____  _____ ____ ___ _   _  ___  ____     '.
       /        ((((   |  _ \| ____|  _ \_ _| | | |/ _ \/ ___|      \
      |        ((((    | |_) |  _| | | | | || |_| | | | \___ \       |
      |       ((((     |  _ <| |___| |_| | ||  _  | |_| |___) |      |
       \     ((((      |_| \_\_____|____/___|_| |_|\___/|____/      /
        '.    (((((                   S.A.S.                      .'
          '-.  ((((((((((((((((((((((((((((((((((((((((((((    .-'
              '---........................................---'
                   S u   D i s t r i b u i d o r   H o s p i t a l a r i o ®

                            ~ Su Distribuidor Hospitalario® ~

          ███████╗██╗   ██╗███████╗ █████╗ ██████╗ ███╗   ███╗██╗███╗   ██╗
          ██╔════╝╚██╗ ██╔╝██╔════╝██╔══██╗██╔══██╗████╗ ████║██║████╗  ██║
          ███████╗ ╚████╔╝ ███████╗███████║██║  ██║██╔████╔██║██║██╔██╗ ██║
          ╚════██║  ╚██╔╝  ╚════██║██╔══██║██║  ██║██║╚██╔╝██║██║██║╚██╗██║
          ███████║   ██║   ███████║██║  ██║██████╔╝██║ ╚═╝ ██║██║██║ ╚████║
          ╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═════╝ ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝





> **Versión:** 1.11.0 · **Fecha:** 2026-09-29 · **Estado:** Etapas 0-8 + Fases 1-7 (plan completo + seguridad)  
> Sistema integral de gestión de inventario IT, usuarios, mantenimiento, hoja de vida por activo, sincronización con OCS Inventory NG, repositorio de documentos, roles/permisos, tickets, préstamos, detección de vencimiento de licencias y gestión de cuentas


## 📊 Estado del Proyecto

| Módulo                        | App Django       | Estado     | Etapa  |
| ----------------------------- | ---------------- | ---------- | ------ |
| 🔐 Autenticación               | `accounts`       | ✅ Completa | 0-1    |
| 📊 Dashboard                   | `core`           | ✅ Completa | 0      |
| 👥 Usuarios                    | `usuarios`       | ✅ Completa | 2      |
| 💻 Inventario                  | `inventario`     | ✅ Completa | 3      |
| 📈 Reportes                    | `reports`        | ✅ Completa | 4      |
| 🔧 Mantenimiento               | `mantenimiento`  | ✅ Completa | 5      |
| 🔑 Contraseñas                 | `passwords`      | ✅ Completa | 6      |
| 🔄 Yule (OCS)                  | `yule`           | ✅ Completa | 7B     |
| 💾 Inventario de software por activo | `inventario` | ✅ Completa | 7B-bis |
| 📦 Vista global de software ("quién tiene qué") | `inventario` | ✅ Completa | 7B-bis |
| 📁 Documentos                  | `documentos`     | ✅ Completa | 8      |
| 🛡️ Administración              | `administracion` | ✅ Completa | Fase 1 |
| 🔳 Etiquetas QR                | `inventario`     | ✅ Completa | Fase 2 |
| 🔔 Notificaciones              | `notificaciones` | ✅ Completa | Fase 3 |
| 📅 Calendario mantenimiento    | `mantenimiento`  | ✅ Completa | Fase 3 |
| 📋 Portal de reporte de fallas | `mantenimiento`  | ✅ Completa | Fase 3 |
| 🎫 Helpdesk / Tickets          | `soporte`        | ✅ Completa | Fase 4 |
| 💠 Licencias de software       | `licencias`      | ✅ Completa | Fase 5 |
| 🔁 Préstamos de equipos        | `prestamos`      | ✅ Completa | Fase 6 |
| 🧪 Tests de cobertura          | todas las apps   | ✅ Completa | Fase 4 |
| 🛡️ Seguridad del login (django-axes) + auditoría de fallos | `accounts` | ✅ Completa | Fase 7 |
| 🔒 HTTPS interno (nginx + cert autofirmado) | infraestructura | ✅ Completa | Fase 7 |

**Producción** (2026-09-29): 24 activos · 1 vinculado a OCS (W11F35F) · 121 programas inventariados · 404 tests en verde. El resto de la flota se está cargando por partes; el sync de software ya corre solo a diario aunque hoy solo tenga un equipo al que leerle.

---

## 🏗️ Stack Técnico

| Componente        | Tecnología                          |
| ----------------- | ----------------------------------- |
| **Backend**       | Django 4.2 + Python 3.11            |
| **Base de Datos** | PostgreSQL 15                       |
| **Frontend**      | Bootstrap 5.3 + HTMX                |
| **Reportes**      | WeasyPrint (PDF) + openpyxl (Excel) |
| **Seguridad**     | Cryptography + Argon2               |
| **Contenedores**  | Docker Compose                      |
| **Proxy Inverso** | Nginx 1.25                          |
| **Red**           | LAN Local (192.168.1.250)           |

---

## 📁 Estructura del Proyecto

```
SysAdmin/
├── docker-compose.yml              ← Orquestación de servicios
├── .env                            ← Variables de entorno (NO commitear)
├── .gitignore
├── requirements.txt
├── setup_server.sh                 ← Setup inicial Ubuntu Server
├── SYSADMIN_HANDOFF.md             ← Documentación técnica completa
├── README.md                       ← Este archivo
├── nginx/                          ← Proxy inverso
│   ├── Dockerfile
│   └── nginx.conf
└── backend/                        ← Aplicación Django
    ├── Dockerfile
    ├── entrypoint.sh               ← Migraciones + collectstatic
    ├── manage.py
    ├── requirements.txt
    ├── static/                     ← CSS + JS + Imágenes
    │   ├── css/sysadmin.css        ← Design system
    │   ├── js/sysadmin.js
    │   └── img/
    ├── templates/
    │   └── base.html               ← Plantilla base (sidebar + topbar)
    ├── sysadmin/                   ← Configuración Django
    │   ├── settings/base.py
    │   ├── urls.py
    │   └── wsgi.py
    ├── accounts/                   ← Autenticación (Login/Logout)
    ├── core/                       ← Dashboard (Estadísticas)
    ├── usuarios/                   ← Gestión de personas
    ├── inventario/                 ← Gestión de activos
    ├── reports/                    ← Reportes y exportes (PDF/Excel)
    ├── mantenimiento/              ← Órdenes de mantenimiento
    ├── passwords/                  ← Vault de contraseñas cifradas
    ├── yule/                       ← Sincronización OCS Inventory NG
    └── documentos/                 ← Manuales, procedimientos y documentos
```

---

## 🚀 Puesta en Marcha

### Paso 1: Preparar Servidor Ubuntu

En el servidor Ubuntu como **root**:

```bash
sudo bash setup_server.sh
```

Este script instala automáticamente:
- Docker + Docker Compose
- Python 3.11
- PostgreSQL client
- Requisitos del sistema

### Paso 2: Copiar Proyecto al Servidor

**Opción A: Via SCP** (desde tu PC)
```bash
scp -r "ruta/local/SysAdmin" usuario@192.168.1.250:/opt/sysadmin/app
```

**Opción B: Via Git**
```bash
git clone https://github.com/tu-usuario/SysAdmin.git /opt/sysadmin/app
```

### Paso 3: Configurar Variables de Entorno

```bash
cd /opt/sysadmin/app
cp .env.example .env
nano .env
```

**Valores obligatorios a cambiar:**

```ini
# Django
SECRET_KEY=generado_con_secrets.token_urlsafe(50)
PASSWORDS_ENCRYPTION_KEY=clave_fernet_de_44_caracteres
DEBUG=False
DJANGO_SETTINGS_MODULE=sysadmin.settings.production
ALLOWED_HOSTS=192.168.1.250,localhost,127.0.0.1

# Base de datos
POSTGRES_DB=sysadmin_db
POSTGRES_USER=sysadmin_user
POSTGRES_PASSWORD=contraseña_segura_aqui
DB_HOST=db
DB_PORT=5432

# Seguridad HTTPS (detrás de nginx)
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
TRUSTED_ORIGINS=https://192.168.1.250:6060

# OCS Configuration (Yule)
OCS_BASE_URL=http://192.168.1.250:8081/ocsapi/v1
OCS_USER=Administrador
OCS_TOKEN=token_ocs_aqui
OCS_VERIFY_SSL=False
```

> **Nota:** `manage.py` y `wsgi.py` cargan `.env` automáticamente en desarrollo con `python-dotenv`. En producción Docker las variables vienen del `env_file` de `docker-compose.yml`.

### Paso 4: Levantar Contenedores

```bash
docker compose up -d --build
```

Verificar que todo esté corriendo:
```bash
docker compose ps
```

Esperado:
```
NAME            STATUS
sysadmin_db     healthy
sysadmin_django healthy
sysadmin_nginx  started
```

### Paso 5: Crear SuperAdmin

```bash
docker exec -it sysadmin_django python manage.py createsuperuser
```

Seguir las instrucciones en pantalla para crear usuario y contraseña.

### Paso 6: Acceder a la Aplicación

Desde cualquier PC de la red LAN (el acceso es **HTTPS** con cert autofirmado → aviso de seguridad esperable al primer ingreso):

```
https://192.168.1.250:6060
```

El puerto `6061` redirige automáticamente de HTTP → HTTPS:

```
http://192.168.1.250:6061   →   https://192.168.1.250:6060
```

Admin panel:
```
https://192.168.1.250:6060/admin
```

---

## 🔧 Comandos Útiles

### Estado y Logs

```bash
# Ver estado de todos los contenedores
docker compose ps

# Ver logs en tiempo real del Django
docker compose logs -f django

# Ver logs del Nginx
docker compose logs -f nginx

# Ver logs de PostgreSQL
docker compose logs -f postgres

# Reiniciar un servicio específico
docker compose restart django

# Detener todos los servicios
docker compose down

# Detener TODO y borrar volúmenes (¡CUIDADO! Borra la BD)
docker compose down -v
```

### Base de Datos y Migraciones

```bash
# Ejecutar migraciones pendientes
docker exec -it sysadmin_django python manage.py migrate

# Crear migraciones desde cambios en models.py
docker exec -it sysadmin_django python manage.py makemigrations

# Ver estado de migraciones
docker exec -it sysadmin_django python manage.py showmigrations

# Recolectar archivos estáticos
docker exec -it sysadmin_django python manage.py collectstatic --noinput
```

### Sincronización OCS (Yule)

```bash
# Sincronización normal (respeta frecuencia mínima)
docker exec -it sysadmin_django python manage.py sync_ocs

# Forzar sincronización sin validar frecuencia
docker exec -it sysadmin_django python manage.py sync_ocs --force

# Sincronizar como usuario específico
docker exec -it sysadmin_django python manage.py sync_ocs --user=admin

# Ver historial en web
# https://192.168.1.250:6060/yule/historial/
```

### Inventario de software (OCS)

```bash
# Simular sin escribir nada (qué cambiaría)
docker exec sysadmin_django python manage.py sincronizar_software --dry-run --verbose

# Sincronizar la flota completa
docker exec sysadmin_django python manage.py sincronizar_software --verbose --pausa 2

# Solo un activo puntual
docker exec sysadmin_django python manage.py sincronizar_software --activo 24 --verbose

# Ver el log del cron diario
tail -f /var/log/sysadmin-software-sync.log
```

El cron corre solo a las **03:07**. Ver `AGENT_RUNBOOK.md`.

Vistas: `/inventario/<pk>/software/` (software del activo) · `/inventario/software/` (qué programas hay y en cuántos activos).

### Backups

```bash
# Crear backup manual de la BD
/opt/sysadmin/backups/backup.sh

# Ver logs del último backup
cat /opt/sysadmin/backups/backup.log

# Listar todos los backups
ls -lh /opt/sysadmin/backups/
```

---

## 📚 Módulos Principales

### 1. Inventario (Etapa 3)

Gestión completa de activos IT con soporte para múltiples tipos de dispositivos.

**Dispositivos soportados:**
- Celulares (IMEI, línea, operador)
- Equipos de escritorio
- Portátiles
- Teléfonos fijos
- Monitores

**Características:**
- ✅ CRUD completo con validación
- ✅ Seguimiento de garantía
- ✅ Historial de movimientos
- ✅ Actas de asignación en PDF
- ✅ **Etiquetas QR imprimibles** (etiqueta individual, selección masiva de hasta 8 por hoja A4 y código QR integrado en la ficha del activo)
- ✅ Exportación a Excel
- ✅ **Importación masiva desde Excel** (plantilla descargable, vista previa, confirmación)
- ✅ **Plantilla Excel** con 39 columnas, 2 ejemplos (Portátil/Celular) y hoja Instrucciones
- ✅ **Inventario de software por activo desde OCS** (programa, versión, editor, fecha de instalación, y si se sigue viendo o se retiró; se actualiza solo cada día)

**Acceso:** `https://192.168.1.250:6060/inventario/`
**Software por activo:** `https://192.168.1.250:6060/inventario/<pk>/software/`
**Todos los equipos, quién tiene qué:** `https://192.168.1.250:6060/inventario/software/`

---

### 2. Usuarios (Etapa 2)

Gestión de personal de la organización.

**Campos:**
- Nombre completo
- Documento de identidad
- Cargo y área
- Correo y teléfono
- Foto de perfil
- Activos asignados

**Características:**
- ✅ CRUD completo con validación
- ✅ Foto de perfil
- ✅ Activos asignados
- ✅ **Importación masiva desde Excel** (plantilla descargable, vista previa, confirmación)
- ✅ **Plantilla Excel** con 6 columnas, 2 ejemplos y hoja Instrucciones

**Acceso:** `https://192.168.1.250:6060/usuarios/`

---

### 3. Reportes (Etapa 4)

Generación de reportes y exportación de datos.

**Reportes disponibles:**
- 📄 PDF de inventario con estilo de marca, columnas configurables y filtro por tipo
- 📄 PDF de usuarios por área
- 📊 Excel de inventario detallado (columnas seleccionables, resumen por categorías, totales)
- 📊 Excel de movimientos (filtrable por fecha)
- 📊 Excel de costos y amortización

**Pantalla de opciones de exportación:** `/inventario/exportar/opciones/` permite elegir formato (Excel/PDF), tipo de dispositivo y columnas.

**Acceso:** `https://192.168.1.250:6060/reports/`

---

### 4. Mantenimiento (Etapa 5)

Gestión de órdenes de mantenimiento preventivo y correctivo.

**Características:**
- Planes de mantenimiento por equipo
- Órdenes con estado y prioridad
- Seguimiento de repuestos
- Costos estimados vs reales
- Historial completo

**Acceso:** `https://192.168.1.250:6060/mantenimiento/`

---

### 5. Contraseñas (Etapa 6)

Vault seguro de credenciales con cifrado.

**Características:**
- ✅ Cifrado simétrico (cryptography)
- ✅ Hash de acceso con Argon2
- ✅ Control de rol (staff/superuser)
- ✅ Auditoría de accesos
- ✅ Exportación segura

**Acceso:** `https://192.168.1.250:6060/passwords/`

---

### 6. Documentos (Etapa 8)

Repositorio centralizado de manuales, procedimientos, políticas y documentos generales.

**Características:**
- ✅ CRUD de documentos con archivo adjunto
- ✅ Categorías personalizables
- ✅ Tipos de documento: manual, procedimiento, política, general
- ✅ Control de versión y fecha de versión
- ✅ Filtros por tipo, categoría y texto
- ✅ Descarga directa de archivos
- ✅ Iconos por tipo de archivo (PDF, Word, Excel, etc.)

**Acceso:** `https://192.168.1.250:6060/documentos/`

---

### 7. Yule - OCS Inventory (Etapa 7B)

Sincronización automática con OCS Inventory NG para detección de equipos.

**Características:**
- ✅ Sincronización bidireccional
- ✅ Retry logic con exponential backoff
- ✅ Búsqueda automática de matches (serial/MAC/hostname)
- ✅ Auditoría completa de sincronizaciones
- ✅ Dashboard con estadísticas
- ✅ Admin customizado

**Configuración requerida:**
```ini
OCS_BASE_URL=https://ocs.tu-empresa.local/ocsapi/v1
OCS_USER=usuario_ocs
OCS_TOKEN=token_ocs_aqui
OCS_VERIFY_SSL=True
```

**Vistas disponibles:**
| URL                        | Descripción                             |
| -------------------------- | --------------------------------------- |
| `/yule/`                   | Dashboard principal                     |
| `/yule/equipos/`           | Lista paginada con filtros              |
| `/yule/equipos/<id>/`      | Detalle del equipo                      |
| `/yule/equipos/sin-match/` | Equipos sin vincular a inventario local |
| `/yule/historial/`         | Auditoría de sincronizaciones           |

**3 formas de sincronizar:**

1. **Web UI** (Recomendado para pruebas)
   ```
   https://192.168.1.250:6060/yule/ → Botón "Sincronizar ahora"
   ```

2. **Django Admin**
   ```
   https://192.168.1.250:6060/admin/yule/configuracionyule/
   ```

3. **Command Line** (Automatización)
   ```bash
   docker exec -it sysadmin_django python manage.py sync_ocs --force
   ```

**Troubleshooting:**

| Problema               | Solución                                           |
| ---------------------- | -------------------------------------------------- |
| No conecta a OCS       | Verificar URL, credenciales, certificados SSL      |
| Equipos sin vincular   | Usar búsqueda de matches por serial/MAC en detalle |
| Sincronización lenta   | Aumentar timeout en client.py (default: 15s)       |
| Error 401 Unauthorized | Regenerar token en OCS Admin                       |

---

## 📋 Tareas Críticas Pendientes

1. **Deploy en servidor**
   - Ejecutar `migrate` (42 migraciones; nuevas: `licencias`, `prestamos`, `soporte`, `mantenimiento` 0002/0003, `administracion` 0002, `yule` 0002, `passwords` 0002/0003, etc.)
   - Reiniciar contenedor Django
   - Verificar módulos Fases 1-6 (tickets, licencias, préstamos) y validación manual de reportes configurables + importación masiva + etiquetas QR

2. **HTTPS (Fase 7)**: el acceso ahora es `https://192.168.1.250:6060` (cert autofirmado en `nginx/certs/`); `http://...:6061` redirige a HTTPS. Al desplegar, levantar con `docker compose up -d --build` y confirmar que https carga sin 500 y el redirect funciona.

3. **Tests**: Suite automatizada — ✅ **404/404 OK** (Fases 1-7 + inventario de software 7B-bis)

4. **Cron del inventario de software**: corre solo a las **03:07**. En un servidor nuevo hay que instalarlo con `sudo bash /opt/sysadmin/app/deploy/instalar_cron_software.sh`.

---

## 📝 Documentación Completa

Para documentación técnica detallada, configuración avanzada, y arquitectura:

**Ver:** [SYSADMIN_HANDOFF.md](SYSADMIN_HANDOFF.md)

**Etiquetas QR — tamaño e impresión:** [ETIQUETAS_IMPRESION.md](ETIQUETAS_IMPRESION.md) (plaqueta física **50 × 30 mm**, definida en `.label` de `etiqueta_pdf.html`)

Este documento contiene:
- Detalles de cada etapa implementada
- Modelos de datos completos
- Estructura de ficheros
- Configuración Django (INSTALLED_APPS, settings)
- Instrucciones para patching
- Cambios históricos (changelog)

---

## 🎨 Design System

El proyecto utiliza un design system consistente:

**Colores:**
- `--sa-primary-light`: Principal suave
- `--sa-primary-dark`: Principal oscuro
- `--sa-bg`: Fondo principal
- `--sa-border`: Bordes

**Fuentes:**
- `Sora`: Interfaz (headings)
- `JetBrains Mono`: Código y datos técnicos

**Componentes:**
- `sa-card`: Tarjetas
- `sa-table`: Tablas
- `sa-stat-*`: Estadísticas
- Bootstrap 5.3 para todo lo demás

---

## ⚙️ Información del Servidor

```
IP: 192.168.1.250
SO: Ubuntu Server 22.04 LTS
Red: LAN Interna
BD: PostgreSQL 15 en contenedor
```

---

## 📅 Changelog

### 2026-09-24 — v1.10.0 · Seguridad del login + HTTPS interno (Fase 7)

- ✅ **django-axes 8.3.1**: rate limit/lockout del login (5 intentos fallidos por usuario+IP → bloqueo con cooloff 1h). Reemplaza el middleware custom `LoginRateLimitMiddleware`. Reset del contador con login exitoso (`AXES_RESET_ON_SUCCESS`). `django-axes==8.3.1` agregada a `requirements.txt`
- ✅ **Mensajes de error genéricos**: `SysAdminAuthenticationForm` ("Usuario o contraseña incorrectos.") — no revela si el usuario existe; mensaje propio para cuenta inactiva
- ✅ **Auditoría de intentos fallidos**: signals en `accounts/signals.py` registran `login_fallido` y `cuenta_bloqueada` (usuario + IP) en `RegistroAuditoria` (módulo `auth`)
- ✅ **Password validators**: min 10 caracteres + similitud con atributos + comunes + numéricos
- ✅ **Headers de seguridad**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin` (verificados en runtime)
- ✅ **Cookies de sesión**: `HttpOnly`, `SameSite=Lax`, sesión expira al cerrar navegador; tiempo de vida 8 h
- ✅ **HTTPS interno LAN**: cert autofirmado en `nginx/certs/` (CN=192.168.1.250, 825 días); nginx con server 443 ssl + redirect 301 de HTTP; accesos `https://192.168.1.250:6060` y `http://...:6061` → https
- ✅ Suite automatizada **313/313 OK al cerrar esta fase** (hoy **404/404**) · `manage.py check` 0 issues · `makemigrations --check` sin cambios

### 2026-09-29 — v1.11.0 · Inventario de software por activo + vista global + cron diario

- ✅ **`SoftwareInstalado`**: una fila por (activo, nombre, versión) con editor, fecha de instalación, última vez visto, fecha de retiro y si sigue presente. Lo retirado no se borra. Migración `0009_softwareinstalado`
- ✅ **Vista por activo** `/inventario/<pk>/software/` y **vista global** `/inventario/software/` (qué programas hay y en cuántos equipos)
- ✅ **Las vistas leen de la base**, no de OCS. Antes cada visita era un request a OCS; con 24 equipos, 24 requests por página
- ✅ **Solo se escriben diferencias**: un reporte idéntico da 0 escrituras
- ✅ **Las bajas solo se cuentan si el reporte llegó de verdad**: un OCS caído o un equipo no vinculado no vacían la base (si no, el lunes "reinstalaría" los 122 programas del fin de semana)
- ✅ **Cron diario a las 03:07** (`/etc/cron.d/sysadmin-sincronizar-software`), log en `/var/log/sysadmin-software-sync.log`
- ✅ **`sincronizar_software`**: comando CLI con `--dry-run`, `--verbose`, `--activo`, `--pausa`; errores aislados por equipo
- ✅ Hook que lee el software de los activos recién vinculados, sin tumbar el sync de hardware si falla
- ✅ Suite automatizada **404/404 OK**

### 2026-09-17 — v1.9.1 · Hoja de vida por activo + Reporte PDF de activos con mantenimiento

- ✅ **Hoja de vida por activo** (HTMX): búsqueda por serial/marca/modelo desde `/mantenimiento/hoja-de-vida/`; botones "Hoja de vida" en las listas de órdenes y planes
- ✅ **PDF de hoja de vida multi-página** (`mantenimiento_hoja_vida_pdf`): fichas de identificación + historial de mantenimiento + checklist + estado de partes (OCS) + software snapshot, generado con WeasyPrint
- ✅ **Reporte de activos con mantenimiento** (`mantenimiento_reportes_activos_pdf`): una fila por activo con al menos un mantenimiento cerrado (serial, marca/modelo, tipo, fecha del último mantenimiento)
- ✅ Suite automatizada **271/271 OK** · `manage.py check` 0 issues

### 2026-09-10 — v1.9.0 · Detección de vencimiento de licencias + Gestión de cuentas

- ✅ Ejecutados los **9 commits del sprint** (grupo §13 del resumen de sesión): `1565d08`→`5094cba` (security, QR, mantenimiento, soporte, licencias, prestamos, cobertura, drift, docs). Working tree limpio, suite 203/203 previo a commits.
- ✅ **Detector de licencias en notificaciones** (`c9f18ac`): nuevo tipo `licencia` en la campana + choice `contrato` en `TIPOS_LICENCIA`. `_detectar_licencias` marca vencidas / por vencer (≤7 días), excluye canceladas y sin fecha; integrdo en `generar_notificaciones` solo para roles con acceso a `licencias`. Migraciones `licencias/0002` + `notificaciones/0002`. 6 tests nuevos.
- ✅ **Gestión de cuentas de usuario** (`36d58bb`): `/administracion/cuentas/` — listado con búsqueda HTMX, crear con contraseña temporal (una sola vez), cambiar rol, activar/desactivar y resetear contraseña. `is_superuser`/`is_staff` **solo para rol `superadmin`**. Guardas anti auto-desmoción/auto-desactivación. 8 tests nuevos.
- ✅ Verificación final: suite **217/217 OK** · `manage.py check` 0 issues · `makemigrations --check` sin cambios · `.env` y `db.sqlite3` no versionados.

### 2026-09-10 — Fase 4: Tests de cobertura

- ✅ Tests para las 7 apps sin cobertura: `core`, `usuarios`, `mantenimiento`, `documentos`, `passwords`, `reports`, `yule` (81 tests nuevos)
- ✅ CRUD completo + permisos por rol + login required en cada módulo
- ✅ PDFs de `reports` probados con WeasyPrint mockeado en `sys.modules` (sin GTK)
- ✅ Fix bug producción: `passwords` registraba `AccesoLog` después de borrar el vault/credencial → `ValueError: save() prohibited`; el log ahora se escribe antes del `delete()`
- ✅ Suite completa: **153/153 tests OK**, `manage.py check` 0 issues

### 2026-09-10 — v1.5.0 · Fase 3 completa (checklist + criticidad + calendario + reportar)

- ✅ **Checklist por orden**: `ChecklistItem` con plantilla en `PlanMantenimiento`; al crear una orden con plan asociado se copian los items como lista de chequeo; toggle HTMX con barra de progreso en el detalle de orden
- ✅ **Criticidad de planes**: campo `criticidad` (`baja/media/alta`) con badge de color en la tabla de planes y el detalle del plan
- ✅ **Calendario de mantenimiento**: FullCalendar CDN + endpoint JSON con ordenes (por fecha de apertura) y planes preventivos (por proxima ejecucion), colores por estado/criticidad
- ✅ **Portal de reporte de fallas**: `/mantenimiento/reportar/` accesible para cualquier usuario autenticado (rol lectura incluido); crea orden en estado `reportada`, tipo `correctivo`, prioridad `alta`
- ✅ **Management command** `generar_notificaciones_mantenimiento` (idempotente: 1 notificación por usuario, sin duplicados al correr 2 veces)
- ✅ 12 tests nuevos en `mantenimiento/tests.py` → suite total **153/153 OK**
- ✅ Migración `mantenimiento/0002_planmantenimiento_criticidad_and_more`

### 2026-09-10 — v1.6.0 · Fase 4: Helpdesk / Tickets (app `soporte`)

- ✅ Nueva app `soporte`: modelo `Ticket` (asunto, descripcion, prioridad, estado abierto/en_proceso/resuelto/cerrado/escalado, solicitante, asignado_a)
- ✅ Portal de creación abierto a cualquier usuario autenticado (`@login_required`); lista/detalle exigen `soporte` lectura; asignar/editar/escalar exigen escritura (módulo nuevo en `PERMISOS_POR_ROL`)
- ✅ Notificación tipo `aviso` al asignar un ticket (`aviso_usuario`, idempotente por `objetokey=ticket:{pk}` — sin duplicados al reasignar)
- ✅ **Escalar ticket → orden de mantenimiento**: botón en el detalle que crea `OrdenMantenimiento` correctiva/abierta con FK `ticket` y prioridad heredada; el ticket pasa a estado `escalado` (no permite duplicar la orden)
- ✅ FK opcional `ticket` en `OrdenMantenimiento` (SET_NULL)
- ✅ Sidebar: enlace "Soporte" condicional por rol
- ✅ 14 tests nuevos en `soporte/tests.py` → suite total **167/167 OK**
- ✅ Migraciones `soporte/0001_initial` + `mantenimiento/0003_ordenmantenimiento_ticket`

### 2026-09-10 — v1.7.0 · Fase 5: Licencias de software (app `licencias`)

- ✅ Nueva app `licencias`: modelo `LicenciaSoftware` (nombre, versión, proveedor, clave/serial, tipo, cantidad, fecha compra/vencimiento, costo, estado, responsable, equipos cubiertos M2M a `inventario.Activo`, observaciones)
- ✅ Estado efectivo calculado: `activa / por_vencer (≤7d) / vencida / cancelada` derivado de vencimiento y estado manual
- ✅ CRUD completo: lista con filtros + estadísticas + detalle + crear/editar/eliminar (confirmación)
- ✅ Exportación **Excel** con headers REDIHOS azul + **PDF** vía WeasyPrint (mock en tests) — patrón `CAMPOS_LICENCIAS` extraíble
- ✅ Módulo `licencias` añadido a `PERMISOS_POR_ROL`: superadmin/admin = escritura; tecnico/lectura = lectura
- ✅ Sidebar: enlace "Licencias" entre Mantenimiento y Documentos
- ✅ Filtro genérico `get_item` para dict en plantillas (`accounts/templatetags/permisos_extras.py`)
- ✅ 19 tests en `licencias/tests.py` → suite total **186/186 OK**
- ✅ Migración `licencias/0001_initial` (generada y validada en BD limpia temporal)

### 2026-09-10 — v1.8.0 · Fase 6: Préstamos de equipos (app `prestamos`)

- ✅ Nueva app `prestamos`: modelo `Prestamo` (activo FK a `inventario.Activo`, solicitante FK a usuario, fecha préstamo, devolución prevista/real, destino, observaciones)
- ✅ Estado calculado: `devuelto > vencido (prevista pasada) > activo`; `dias_retraso` para vencidos
- ✅ Validación de préstamo vigente: un equipo no puede prestarse dos veces mientras no se registre devolución
- ✅ CRUD + "Registrar devolución" (POST, idempotente) — sin eliminar para preservar el historial
- ✅ Lista con filtros (búsqueda + estado) y estadísticas (total/activos/vencidos/devueltos)
- ✅ Módulo `prestamos` añadido a `PERMISOS_POR_ROL`: superadmin/admin/tecnico = escritura; lectura = lectura
- ✅ Sidebar: enlace "Préstamos" tras Licencias
- ✅ 16 tests en `prestamos/tests.py` → suite total **202/202 OK** · `manage.py check` 0 issues
- ✅ Migración `prestamos/0001_initial` (generada y validada en BD limpia temporal)
- 🏁 **Plan por fases completado** (1-6)

### 2026-09-10 — v1.8.1 · Corrección de BD local + drift de migraciones

- ✅ `db.sqlite3` local reconstruida de cero (historial de migraciones inconsistente pre-existente sin `accounts_customuser` y sin datos de negocio): `migrate` aplica las **42 migraciones** en orden; superuser dev `admin` (superadmin) y singleton `ConfiguracionSistema` creados. BD antigua respaldada en `backend/db.sqlite3.legacy_20260910`.
- ✅ Drift resuelto: `yule/0002` (renombres de índices) y `administracion/0002` (choices de `modulo` con los módulos Fases 4-6); `makemigrations --check` → *No changes detected*.
- ✅ Suite completa **202/202 OK** · `manage.py check` 0 issues.

### 2026-09-10 — Fase 2: Etiquetas QR para activos

- ✅ Código QR por activo (URL de la ficha) en PNG
- ✅ PDF de etiqueta individual (50×30 mm) con datos del equipo
- ✅ Selección masiva de activos → PDF con hasta 8 etiquetas por hoja A4
- ✅ Vista previa del QR en la ficha del activo + botones en lista y tabla
- ✅ Dependencia nueva `qrcode==8.2`
- ✅ Registro de fases en `FASES.md`

### 2026-09-10 — Fase 1: Módulo de Administración (roles, permisos y auditoría)

- ✅ Roles `superadmin`/`admin`/`tecnico`/`lectura` + matriz de permisos
- ✅ Decorador `@requiere_permiso` aplicado en todas las vistas de los módulos
- ✅ Nueva app `administracion`: auditoría de eventos (incl. login/logout) y configuración del sistema
- ✅ Sidebar condicional por rol (template tag `tiene_permiso`)
- ✅ WeasyPrint con imports locales (herramientas de desarrollo locales habilitadas)
- ✅ Tests automatizados: 61/61 OK (suite completa en `accounts`, `administracion`, `inventario`, `notificaciones`, `yule`)

### 2026-09-09 — Post-v1.1.0: Importación masiva Activos + Usuarios + Plantillas Excel

- ✅ **Importación masiva de Activos**: subir .xlsx → vista previa con estado por fila (OK/Duplicado/Error) → confirmar
- ✅ **Importación masiva de Usuarios**: mismo patrón, vista previa, confirmación
- ✅ **Plantillas Excel descargables** para ambos módulos (botón en UI):
  - Activos: 39 columnas, 2 ejemplos (Portátil/Celular), hoja Instrucciones completa
  - Usuarios: 6 columnas, 2 ejemplos, hoja Instrucciones con formato de nombre
- ✅ Parser robusto: mapea labels exactos de CAMPOS_INVENTARIO, normaliza choices/moneda/fechas/booleanos
- ✅ Race guard: doble verificación de serial/documento en confirmación
- ✅ Botón "Descargar plantilla" en ambas pantallas de importación
- ✅ Commit `d952a6f`

### 2026-09-04 — Post-v1.1.0: Reportes configurables

### 2026-09-03 — v1.1.0: Catálogo en activos, fixes y módulo Documentos

- ✅ Nuevo módulo `documentos`: repositorio de manuales, procedimientos, políticas y documentos generales
- ✅ Campo `Activo.catalogo` (FK a `CatalogoModelo`) con autocompletado de marca/modelo en el formulario
- ✅ Campo `Activo.nombre_equipo` para equipos de escritorio/portátil
- ✅ Fix de errores 500 en mantenimiento, asignaciones, reportes y exportación PDF
- ✅ Fix visual de stat-cards en detalle de activo
- ✅ Mejoras en exportación Excel de inventario (48 columnas con estilo)
- ✅ PDFs de actas y reportes abren en nueva pestaña
- ✅ Puerto de acceso cambiado a `6060` (evita `ERR_UNSAFE_PORT`)
- ✅ Healthcheck en contenedor Django y dependencia `condition: service_healthy` para Nginx
- ✅ Commit `d9ee7cd` tag `v1.1.0`

### 2026-06-05 — Yule 7B Completada

- ✅ Sincronización OCS Inventory implementada (~1900 líneas)
- ✅ Modelos: EquipoOCS, SincronizacionLog, ConfiguracionYule
- ✅ Cliente con retry logic exponencial (1s, 2s, 4s)
- ✅ 7 vistas web + 5 templates responsive
- ✅ Admin customizado con badges y estadísticas
- ✅ Management command `sync_ocs` con flags
- ✅ Búsqueda automática de matches en inventario
- ✅ Documentación consolidada en README + HANDOFF

### 2026-05-10 — Etapas 4-6 Completadas

- Reportes (4): PDF + Excel, filtros por fecha
- Mantenimiento (5): Planes, órdenes, repuestos
- Contraseñas (6): Vault cifrado, auditoría

### 2026-05-04 — Etapas 0-3 Completadas

- Fundación Django + Docker + Nginx
- Autenticación con sesión 30min
- Gestión de usuarios
- Inventario 5 tipos dispositivos + movimientos

---

## 🤝 Soporte

Para issues, contactar al equipo de sistemas.

Para documentación técnica completa, ver **SYSADMIN_HANDOFF.md**

---

**Última actualización:** 2026-09-24  
**Proyecto:** 100% Funcional · Listo para producción
