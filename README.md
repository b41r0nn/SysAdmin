# SysAdmin · Sistema de Gestión IT

> **Versión:** 1.1.0 · **Fecha:** 2026-09-09 · **Estado:** Etapas 0-7B + Documentos Completas + Importación Masiva  
> Sistema integral de gestión de inventario IT, usuarios, mantenimiento, sincronización con OCS Inventory NG y repositorio de documentos

---

## 📊 Estado del Proyecto

| Módulo          | App Django      | Estado     | Etapa |
| --------------- | --------------- | ---------- | ----- |
| 🔐 Autenticación | `accounts`      | ✅ Completa | 0-1   |
| 📊 Dashboard     | `core`          | ✅ Completa | 0     |
| 👥 Usuarios      | `usuarios`      | ✅ Completa | 2     |
| 💻 Inventario    | `inventario`    | ✅ Completa | 3     |
| 📈 Reportes      | `reports`       | ✅ Completa | 4     |
| 🔧 Mantenimiento | `mantenimiento` | ✅ Completa | 5     |
| 🔑 Contraseñas   | `passwords`     | ✅ Completa | 6     |
| 🔄 Yule (OCS)    | `yule`          | ✅ Completa | 7B    |
| 📁 Documentos    | `documentos`    | ✅ Completa | 8     |

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
nano .env
```

**Valores obligatorios a cambiar:**

```ini
# Django
SECRET_KEY=generado_con_secrets.token_urlsafe(50)
DEBUG=False
ALLOWED_HOSTS=192.168.1.250,localhost,127.0.0.1

# Base de datos
DB_ENGINE=django.db.backends.postgresql
DB_NAME=sysadmin_db
DB_USER=sysadmin_user
DB_PASSWORD=contraseña_segura_aqui
DB_HOST=postgres
DB_PORT=5432

# OCS Configuration (Yule)
OCS_BASE_URL=https://ocs.tu-empresa.local/ocsapi/v1
OCS_USER=usuario_ocs
OCS_TOKEN=token_ocs_aqui
OCS_VERIFY_SSL=True
```

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
CONTAINER       STATUS
sysadmin_postgres_1     Up
sysadmin_django_1       Up
sysadmin_nginx_1        Up
```

### Paso 5: Crear SuperAdmin

```bash
docker exec -it sysadmin_django python manage.py createsuperuser
```

Seguir las instrucciones en pantalla para crear usuario y contraseña.

### Paso 6: Acceder a la Aplicación

Desde cualquier PC de la red LAN:

```
http://192.168.1.250
```

Admin panel:
```
http://192.168.1.250/admin
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
# http://192.168.1.250/yule/historial/
```

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
- ✅ Exportación a Excel
- ✅ **Importación masiva desde Excel** (plantilla descargable, vista previa, confirmación)
- ✅ **Plantilla Excel** con 39 columnas, 2 ejemplos (Portátil/Celular) y hoja Instrucciones

**Acceso:** `http://192.168.1.250/inventario/`

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

**Acceso:** `http://192.168.1.250/usuarios/`

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

**Acceso:** `http://192.168.1.250/reports/`

---

### 4. Mantenimiento (Etapa 5)

Gestión de órdenes de mantenimiento preventivo y correctivo.

**Características:**
- Planes de mantenimiento por equipo
- Órdenes con estado y prioridad
- Seguimiento de repuestos
- Costos estimados vs reales
- Historial completo

**Acceso:** `http://192.168.1.250/mantenimiento/`

---

### 5. Contraseñas (Etapa 6)

Vault seguro de credenciales con cifrado.

**Características:**
- ✅ Cifrado simétrico (cryptography)
- ✅ Hash de acceso con Argon2
- ✅ Control de rol (staff/superuser)
- ✅ Auditoría de accesos
- ✅ Exportación segura

**Acceso:** `http://192.168.1.250/passwords/`

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

**Acceso:** `http://192.168.1.250/documentos/`

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
   http://192.168.1.250/yule/ → Botón "Sincronizar ahora"
   ```

2. **Django Admin**
   ```
   http://192.168.1.250/admin/yule/configuracionyule/
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

1. **Deploy v1.1.0 en servidor**
   - Ejecutar `migrate` para aplicar migraciones de inventario y documentos
   - Reiniciar contenedor Django
   - Verificar módulo Documentos y catálogo de activos

2. **Tests**: Suite de tests automatizados (TODO futuro)

---

## 📝 Documentación Completa

Para documentación técnica detallada, configuración avanzada, y arquitectura:

**Ver:** [SYSADMIN_HANDOFF.md](SYSADMIN_HANDOFF.md)

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

**Última actualización:** 2026-09-09  
**Proyecto:** 100% Funcional · Listo para producción
