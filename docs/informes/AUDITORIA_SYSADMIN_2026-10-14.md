# Auditoría SysAdmin 2026-10-14

> Documento de la auditoría (commit auditado `7230125`). Especificación de las correcciones aplicadas en la rama `fix/auditoria-2026-10-14`.

---

sigue al detalle estas instrucciones Correcciones de la auditoría SysAdmin (2026-10-14)

Pegar completo. Origen: AUDITORIA_SYSADMIN_2026-10-14.md (commit auditado 7230125). Ejecutor: Kimi en la máquina local de Bairon (VS Code / PowerShell). Nada de esto se ejecuta en el servidor de producción.

0. REGLAS GLOBALES (obligatorias, aplican a todos los bloques)
Alcance estricto. Haz solo lo escrito aquí. Si algo "mejorable" aparece en el camino, anótalo en el reporte final, no lo toques.
Si el código real no coincide con lo descrito (otra línea, otro nombre, otra estructura): PARA y reporta exactamente qué difiere. No improvises ni adaptes por tu cuenta.
Un bloque a la vez, en el orden dado. Al terminar cada bloque: corre los tests indicados, muestra el resultado real (copiado, no resumido) y git diff --stat + git diff de ese bloque, propone el mensaje de commit y ESPERA el "ejecuta" de Bairon antes de seguir.
Git: rama nueva fix/auditoria-2026-10-14 desde master. Prohibido: git commit, git push, git add -A, git add ., git reset --hard, git checkout -- ., git stash drop sin OK explícito de Bairon. Cuando Bairon apruebe un bloque, git add solo los archivos de ese bloque (lista en cada bloque) y commit con el mensaje propuesto.
Nunca: conectarte por SSH, tocar /opt/sysadmin, usar credenciales, ejecutar docker compose contra el servidor, editar .env, borrar registros de BD. Convención del proyecto: nunca borrar registros (desactivar), fecha_creacion/fecha_actualizacion, messages.* en escrituras, comentarios/UI en español.
Tests. Cada cambio de comportamiento lleva test nuevo (se indican). Nunca cambies un test existente para "hacerlo pasar" salvo el que se indica explícitamente (B1). Si un test existente falla por tu cambio, para y reporta.
Salida truncada de PowerShell ("Click to expand"): redirige a archivo y léelo:
powershell
   cd backend
   $env:SECRET_KEY="test-key"; $env:DEBUG="False"; $env:SECURE_SSL_REDIRECT="False"; $env:DJANGO_SETTINGS_MODULE="sysadmin.settings.local"
   Remove-Item Env:POSTGRES_DB -ErrorAction SilentlyContinue
   python manage.py test --noinput 2>&1 | Out-File -Encoding utf8 "$env:TEMP\sysadmin_tests.txt"
   Get-Content "$env:TEMP\sysadmin_tests.txt" -Tail 25

Para un solo app: python manage.py test accounts --noinput. 8. Antes de empezar (PRE-VUELO):

git status debe estar limpio y en master actualizado (git log -1 --oneline → debe ser 7230125 o posterior; reporta el hash).
git checkout -b fix/auditoria-2026-10-14.
Corre la suite completa. Línea base esperada: Ran 406 tests … FAILED (failures=1), única falla accounts.tests.LoginSeguridadTests.test_cookies_sesion_seguras (180 != 28800). Si hay más fallas o distinto conteo, para y reporta.
Formato de reporte por bloque: (a) qué cambiaste, archivo por archivo; (b) salida real de tests; (c) git diff --stat; (d) lo que no pudiste hacer o difiere; (e) mensaje de commit propuesto.

Orden: Fase 1 B1→B3 (urgente) · Fase 2 B4→B7 · Fase 3 B8→B10 · Fase 4 B11→B13. Al cerrar cada fase, resumen y espera.

FASE 1
B1 — Sesión: timeout real por inactividad + arreglar test rojo (hallazgo A3)

Problema verificado: backend/sysadmin/settings/base.py:139 tiene SESSION_COOKIE_AGE = 180. Sin SESSION_SAVE_EVERY_REQUEST, la expiración no se renueva con la actividad: el usuario es expulsado 3 min después del login aunque esté trabajando. Además accounts/tests.py:222 aún asserta 28800.

Decisión ya tomada (no cambiar): se mantiene el valor de 180 s como default (lo eligió Bairon en b9c8541), pero ahora configurable por entorno. (Bairon puede subirlo vía .env; recomendado 900–1800.)

Cambios exactos:

backend/sysadmin/settings/base.py, reemplazar las líneas
python
   SESSION_EXPIRE_AT_BROWSER_CLOSE = True
   SESSION_COOKIE_AGE = 180  # 3 minutos (inactividad)

por

python
   SESSION_EXPIRE_AT_BROWSER_CLOSE = True
   # Timeout por INACTIVIDAD (segundos). SAVE_EVERY_REQUEST renueva la expiración
   # en cada petición; sin él, el tiempo cuenta desde el login y no desde la última actividad.
   SESSION_COOKIE_AGE = int(os.environ.get('SESSION_COOKIE_AGE', '180'))
   SESSION_SAVE_EVERY_REQUEST = True

(SESSION_COOKIE_HTTPONLY y SESSION_COOKIE_SAMESITE quedan igual.) 2. backend/accounts/tests.py línea 222: reemplazar self.assertEqual(settings.SESSION_COOKIE_AGE, 28800) por

python
   self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
   self.assertGreaterEqual(settings.SESSION_COOKIE_AGE, 60)
Test nuevo en la misma clase LoginSeguridadTests (lee su setUp para usar el nombre real del usuario de prueba; no inventes atributos):
python
   def test_sesion_se_renueva_con_actividad(self):
       from django.contrib.sessions.models import Session
       self.client.force_login(<usuario del setUp>)
       antes = Session.objects.get().expire_date
       self.client.get(reverse("core:dashboard"))
       despues = Session.objects.get().expire_date
       self.assertGreater(despues, antes)
.env.example: añadir bajo la sección Django # Segundos de inactividad antes de cerrar sesión (recomendado 900-1800; default 180) y SESSION_COOKIE_AGE=180.
Docs vigentes (NO tocar docs/sesiones/*, son históricas): grep -rn "28800\|8 h\b\|8h" FASES.md README.md AGENTS.md AGENT_RUNBOOK.md CHECKLIST_DEPLOY.md y corrige solo las menciones al timeout de sesión (FASES.md:391 como mínimo) para que digan: "timeout por inactividad configurable con SESSION_COOKIE_AGE (default 180 s) + SESSION_SAVE_EVERY_REQUEST=True".
Verifica que no haya polling que mantenga viva la sesión: grep -rn "hx-trigger=.*every\|setInterval" backend --include=*.html --include=*.js. Reporta el resultado (en la auditoría no había ninguno).

Archivos del commit: backend/sysadmin/settings/base.py, backend/accounts/tests.py, .env.example, FASES.md (+ cualquier doc vigente que hayas corregido). Verificación: python manage.py test accounts --noinput → todo OK; suite completa → 407 tests, 0 fallas (406 + 1 nuevo). Commit propuesto: fix(session): timeout por inactividad real (SAVE_EVERY_REQUEST) y test alineado

B2 — Cerrar /media/ sin autenticación (hallazgo A2)

Problema verificado: nginx/nginx.conf (location /media/ { alias /app/media/; }) sirve actas firmadas, PDFs de actas, documentos y fotos sin login y saltándose los permisos por rol.

Diseño (no lo cambies): /media/<ruta> pasa a Django (vista protegida, login + permiso por módulo). En producción Django responde con X-Accel-Redirect a una ubicación internal de nginx que sirve el archivo; en desarrollo/tests Django sirve el archivo con FileResponse. Las plantillas siguen usando .url (/media/...) sin cambios.

Cambios exactos:

backend/core/views.py (si no existe, créalo; si existe, añade al final). Imports necesarios: mimetypes, posixpath, pathlib.Path, django.conf.settings, django.contrib.auth.decorators.login_required, django.http.FileResponse/Http404/HttpResponse, accounts.permisos.PERMISOS_POR_ROL.
python
   # Prefijo de MEDIA_ROOT -> módulo cuyo permiso protege esos archivos.
   MEDIA_PERMISOS = (
       ("usuarios/fotos/", "usuarios"),
       ("inventario/fotos/", "inventario"),
       ("inventario/actas/", "inventario"),
       ("mantenimiento/fotos/", "mantenimiento"),
       ("documentos/", "documentos"),
   )
   # Tipos que se pueden mostrar en el navegador; el resto se fuerza a descarga.
   MEDIA_INLINE = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}

   @login_required
   def media_protegido(request, ruta):
       limpio = posixpath.normpath(ruta)
       if (
           "\x00" in ruta
           or "\\" in ruta
           or limpio != ruta          # rechaza '..', '//', './', rutas no normalizadas
           or limpio.startswith(("/", ".."))
       ):
           raise Http404
       modulo = next((m for pref, m in MEDIA_PERMISOS if limpio.startswith(pref)), None)
       if modulo is None:
           raise Http404                 # prefijo no registrado: denegar por defecto
       if not request.user.is_superuser:
           nivel = PERMISOS_POR_ROL.get(request.user.rol, {}).get(modulo, "ninguno")
           if nivel == "ninguno":
               raise Http404
       raiz = Path(settings.MEDIA_ROOT).resolve()
       destino = (raiz / limpio).resolve()
       if raiz not in destino.parents or not destino.is_file():
           raise Http404
       tipo = mimetypes.guess_type(destino.name)[0] or "application/octet-stream"
       disposicion = "inline" if tipo in MEDIA_INLINE else "attachment"
       if getattr(settings, "MEDIA_ACCEL_REDIRECT", False):
           resp = HttpResponse()
           resp["X-Accel-Redirect"] = f"/_protegido/{limpio}"
       else:
           resp = FileResponse(destino.open("rb"))
       resp["Content-Type"] = tipo
       resp["Content-Disposition"] = f'{disposicion}; filename="{destino.name}"'
       resp["X-Content-Type-Options"] = "nosniff"
       resp["Cache-Control"] = "private, max-age=3600"
       return resp

(Si core/views.py ya importa algunos de esos nombres, no dupliques imports.)

backend/sysadmin/urls.py: añade (antes de cualquier otra ruta que pueda capturar media/, p. ej. justo tras path('admin/', ...)):
python
   from core.views import media_protegido
   path('media/<path:ruta>', media_protegido, name='media'),

y elimina el bloque final

python
   if settings.DEBUG:
       urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

junto con los imports settings y static si quedan sin uso (así desarrollo y producción pasan por la misma vista).

backend/sysadmin/settings/base.py: añade MEDIA_ACCEL_REDIRECT = False junto a MEDIA_ROOT. production.py: añade MEDIA_ACCEL_REDIRECT = True.
nginx/nginx.conf: en el bloque server HTTPS elimina
nginx
   location /media/ {
       alias /app/media/;
   }

y añade

nginx
   # Solo accesible vía X-Accel-Redirect desde Django (vista media_protegido).
   location /_protegido/ {
       internal;
       alias /app/media/;
       add_header X-Content-Type-Options "nosniff" always;
   }

(/media/... ahora cae en location / → Django.)

Tests nuevos en backend/core/tests.py (créalo si no existe; usa tempfile.TemporaryDirectory + override_settings(MEDIA_ROOT=...); crea los usuarios con los helpers/estilo de los tests existentes en accounts/tests.py):
anónimo → GET /media/usuarios/fotos/x.png responde 302 a login (aunque el archivo exista);
usuario lectura pide /media/inventario/fotos/a.png existente → 200, Content-Type: image/png, Content-Disposition empieza con inline;
usuario con permiso "ninguno" sobre el módulo (p. ej. rol tecnico pidiendo /media/documentos/...? verifica en PERMISOS_POR_ROL cuál rol tiene "ninguno" en qué módulo; usa un caso real, p. ej. administracion no aplica porque no hay prefijo) → si ningún par (rol, módulo-con-prefijo) es "ninguno", prueba con override/parche de PERMISOS_POR_ROL; reporta lo que hiciste;
ruta usuarios/fotos/../../.env y //etc/passwd y inventario/actas/..%2f.. → 404;
prefijo no registrado (otro/a.png) → 404 aunque exista;
archivo .html bajo documentos/ → Content-Disposition empieza con attachment;
con override_settings(MEDIA_ACCEL_REDIRECT=True): respuesta 200, header X-Accel-Redirect == "/_protegido/inventario/fotos/a.png", cuerpo vacío;
test de cobertura de prefijos (anti-fuga futura): recorre django.apps.apps.get_models(), para cada campo FileField/ImageField toma field.upload_to (string), recorta en el primer %, y afirma que empieza con alguno de los prefijos de MEDIA_PERMISOS. Debe pasar hoy con los 7 campos de upload existentes (usuarios/fotos/, documentos/%Y/%m/, mantenimiento/fotos/ ×2, inventario/fotos/, inventario/actas/pdf/, inventario/actas/firmadas/).

Archivos del commit: backend/core/views.py, backend/core/tests.py, backend/sysadmin/urls.py, backend/sysadmin/settings/base.py, backend/sysadmin/settings/production.py, nginx/nginx.conf. Verificación: python manage.py test core --noinput OK; suite completa 0 fallas. Verifica a mano en dev (python manage.py runserver con SQLite local): subir una foto a un activo, abrirla con sesión → se ve; en ventana privada (sin sesión) /media/inventario/fotos/<archivo> → redirige a login. Nota para Bairon (no Kimi): el deploy requiere reconstruir la imagen de nginx (COPY nginx.conf): docker compose build nginx && docker compose up -d nginx, más --force-recreate django. Commit propuesto: fix(seguridad): servir /media/ solo con login y permiso por módulo (X-Accel-Redirect)

B3 — Dependencias con CVEs (hallazgo A1)

Cambios exactos en backend/requirements.txt (versiones = las que pip-audit reportó como corrección):

Paquete	De	A
Django	4.2.13	4.2.30
gunicorn	21.2.0	22.0.0
Pillow	10.3.0	12.3.0
cryptography	42.0.8	49.0.0
requests	2.32.3	2.33.0
python-dotenv	1.0.1	1.2.2

WeasyPrint, pydyf, openpyxl, qrcode, django-axes, django-htmx, psycopg2-binary, argon2-cffi, python-decouple no se tocan en este bloque.

Procedimiento:

Crea un venv nuevo con Python 3.11 (py -3.11 -m venv $env:TEMP\venv_audit), instala pip install -r backend/requirements.txt. Si algún pin no se resuelve (versión inexistente / incompatible con Py3.11), para y reporta el error literal; no cambies a otra versión por tu cuenta.
Suite completa → 0 fallas.
Humo manual obligatorio (los tests mockean partes; esto prueba las libs reales). Con runserver local y un activo con datos: (a) descargar un PDF de acta (generar_acta_pdf) → abre y se ve bien; (b) etiqueta QR PDF → QR escaneable/legible; (c) export Excel de inventario con logo (usa Pillow) → abre en Excel; (d) guardar una credencial en el vault y revelarla (usa cryptography/Fernet) → coincide; (e) página con foto de activo. Reporta cada uno como OK/FALLA con detalle.
pip install pip-audit; pip-audit -r backend/requirements.txt --no-deps --disable-pip y pega la salida completa (se espera que sigan apareciendo WeasyPrint 60.2 y posiblemente Django 4.2.x sin fix; no los persigas).
B3b (solo prueba, no commit): en otro venv aparte, prueba WeasyPrint==70.0 (+ la versión de pydyf que pida pip). Corre la suite y el humo (a) y (b). Solo reporta si funciona; no modifiques requirements.txt por esto. Bairon decide después.
Django 5.2 LTS: FUERA DE ALCANCE. No lo intentes; será un prompt aparte.

Archivos del commit: backend/requirements.txt. Nota para Bairon (no Kimi): deploy exige docker compose build django (cambian dependencias) y up -d --force-recreate django. Commit propuesto: chore(deps): Django 4.2.30, gunicorn 22, Pillow 12.3, cryptography 49, requests 2.33, python-dotenv 1.2.2

— FIN FASE 1: resumen y espera —

FASE 2
B4 — Atomicidad en movimientos de inventario e importaciones (hallazgo M1)

Problema verificado: asignar_activo, devolver_activo, trasladar_activo (backend/inventario/views.py, líneas ≈289, 356, 396) y las confirmaciones de importación hacen varias escrituras sin transacción y sin bloqueo; _siguiente_numero_interno (inventario/models.py:37) usa Max()+1 con carrera.

Cambios exactos:

inventario/views.py: asegura from django.db import IntegrityError, transaction, from django.core.exceptions import ValidationError y import logging + logger = logging.getLogger(__name__) (si no existen).
asignar_activo: conserva el GET/guard inicial. En el POST válido, envuelve todo el cuerpo en una transacción con el activo bloqueado y re-validado:
python
   if form.is_valid():
       with transaction.atomic():
           activo = Activo.objects.select_for_update().get(pk=pk)
           if activo.estado != "disponible":
               messages.error(request, "Solo se pueden asignar activos disponibles.")
               return redirect("inventario:detalle", pk=activo.pk)
           asignacion = form.save(commit=False)
           asignacion.activo = activo
           asignacion.fecha_asignacion = timezone.now().date()
           asignacion.save()
           Movimiento.objects.create(...)      # sin cambios
           acta = ActaAsignacion.objects.create(asignacion=asignacion)
           encolar_email(...)                  # sin cambios
           activo.estado = "asignado"
           activo.save(update_fields=["estado", "fecha_actualizacion"])
       messages.success(request, f"Activo asignado a {asignacion.usuario.nombre_completo}.")
       return redirect("inventario:detalle", pk=activo.pk)

Verifica antes que Activo tiene el campo fecha_actualizacion con auto_now=True; si el nombre difiere, usa el real e inclúyelo en update_fields (los campos auto_now solo se actualizan si están en update_fields). Conserva textos y argumentos originales de Movimiento/encolar_email idénticos.

devolver_activo: mismo patrón: dentro de with transaction.atomic(): → activo = Activo.objects.select_for_update().get(pk=pk), re-consultar asignacion = activo.asignaciones.filter(activa=True).first(); si ya no hay, messages.error("El activo no tiene una asignación activa.") + redirect. Luego las mismas escrituras (asignación inactiva → Movimiento → activo.estado="disponible" con update_fields=["estado","fecha_actualizacion"]).
trasladar_activo: with transaction.atomic(): con select_for_update() sobre el activo y re-consulta de asignacion_actual; mantiene las 3 escrituras y el ActaAsignacion + encolar_email dentro. La validación "usuario destino distinto" queda como está (fuera o dentro, pero sin romper el return render existente).
inventario/models.py — Activo.save(): reemplaza
python
   def save(self, *args, **kwargs):
       if self.numero_interno is None:
           self.numero_interno = _siguiente_numero_interno()
       super().save(*args, **kwargs)

por

python
   def save(self, *args, **kwargs):
       if self.numero_interno is not None:
           return super().save(*args, **kwargs)
       # Max()+1 puede chocar si dos altas ocurren a la vez: reintentar con savepoint.
       for intento in range(5):
           self.numero_interno = _siguiente_numero_interno()
           try:
               with transaction.atomic():
                   return super().save(*args, **kwargs)
           except IntegrityError:
               self.numero_interno = None
               if intento == 4:
                   raise

(añade from django.db import IntegrityError, transaction en models.py si falta). Verifica que los tests existentes de numero_interno siguen verdes.

confirmar_importar_activos (≈línea 1036) y confirmar_importar_usuarios (usuarios/views.py ≈143): reemplaza el try/except Exception por fila por savepoint + excepciones concretas + log:
python
   try:
       with transaction.atomic():
           Activo.objects.create(**datos)          # Usuario.objects.create(**datos) en usuarios
       creados += 1
   except (IntegrityError, ValidationError, ValueError, TypeError) as exc:
       logger.warning("Importación: fila con error (%s): %s", <serial o documento>, exc)
       errores += 1

En activos, el parseo date.fromisoformat(fc) con except Exception → except ValueError. (Necesario el savepoint: en PostgreSQL un IntegrityError sin savepoint deja la transacción inutilizable.) Añade logger en usuarios/views.py si falta.

except Exception / pass en el flujo de importación (inventario/views.py líneas ≈918, 926, 932, 1010, 1062, 1071; usuarios/views.py ≈117, 171): lee cada try; si el cuerpo es un parseo de número/fecha, cambia a las excepciones concretas (ValueError, InvalidOperation de decimal, TypeError); el try/except/pass de la línea ≈926 (formatos de fecha) → except ValueError: continue. Si es un límite deliberado (lectura de archivo Excel corrupto), conserva except Exception pero añade logger.exception(...) y mensaje al usuario existente. Reporta tabla: línea → decisión.

Tests nuevos (en inventario/tests.py y usuarios/tests.py, con el estilo de los existentes):

asignar_activo con patch("inventario.views.encolar_email", side_effect=RuntimeError): with self.assertRaises(RuntimeError): self.client.post(...); después Asignacion.objects.count()==0, Movimiento sin filas nuevas, ActaAsignacion 0 y activo.estado=="disponible" (rollback completo).
asignar_activo sobre activo asignado (POST) → no crea Asignacion nueva y muestra el mensaje de error.
devolver_activo y trasladar_activo: mismo patrón de rollback con Movimiento.objects.create parcheado para fallar → la asignación activa sigue activa.
Activo.save(): parchea _siguiente_numero_interno con side_effect=[1000, 1001] habiendo ya un activo con numero_interno=1000 → el segundo alta termina con 1001 (reintento exitoso).
Importación de activos: archivo con 3 filas válidas donde Activo.objects.create falla con IntegrityError en la 2ª (parche con side_effect) → creados=2, errores=1, y la sesión sigue utilizable (el mensaje final correcto). Igual para usuarios.

Archivos del commit: backend/inventario/views.py, backend/inventario/models.py, backend/usuarios/views.py, backend/inventario/tests.py, backend/usuarios/tests.py. Verificación: python manage.py test inventario usuarios --noinput, luego suite completa. Commit propuesto: fix(inventario): transacciones y bloqueo en asignar/devolver/trasladar, savepoints en importaciones, numero_interno con reintento

B5 — IP real para axes y auditoría (hallazgo M2)

Problema verificado: django-ipware no está instalado, así que axes cae a REMOTE_ADDR (= IP del contenedor nginx) y ignora cualquier AXES_IPWARE_*. Todos los clientes comparten IP → el bloqueo efectivo es por usuario (cualquiera en la LAN puede bloquear al superadmin 1 h). Las señales de auditoría toman el primer valor de X-Forwarded-For, que el cliente puede falsificar.

Cambios exactos:

nginx/nginx.conf, en location /: cambia proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; por proxy_set_header X-Forwarded-For $remote_addr; (nginx es el único proxy; un solo valor, no falsificable).
backend/core/utils.py (crear si no existe, o añadir):
python
   def get_client_ip(request):
       """IP real del cliente detrás de nginx.

       nginx fija X-Forwarded-For = $remote_addr. Se toma el ÚLTIMO valor (el que
       agregó nuestro proxy), nunca el primero, que el cliente puede falsificar.
       Sin proxy (desarrollo) cae a REMOTE_ADDR.
       """
       if not request or not getattr(request, "META", None):
           return None
       xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
       if xff:
           return xff.split(",")[-1].strip() or request.META.get("REMOTE_ADDR")
       return request.META.get("REMOTE_ADDR")
base.py, en la sección de axes: AXES_CLIENT_IP_CALLABLE = "core.utils.get_client_ip".
accounts/signals.py y administracion/signals.py: elimina las funciones locales _request_ip y usa from core.utils import get_client_ip en sus llamadas. En accounts/signals.py elimina el BOM (primer carácter invisible U+FEFF): reescribe el archivo en UTF-8 sin BOM (verifica: python -c "print(open('backend/accounts/signals.py','rb').read(3))" no debe dar b'\xef\xbb\xbf').
Tests nuevos (core/tests.py y accounts/tests.py):
get_client_ip con HTTP_X_FORWARDED_FOR="9.9.9.9, 10.0.0.5" → "10.0.0.5"; sin header → REMOTE_ADDR; request None → None.
Login fallido con HTTP_X_FORWARDED_FOR="10.0.0.5" (kwarg del client) → AccessAttempt.objects.get(username=...).ip_address == "10.0.0.5"; otro intento desde "10.0.0.6" no cuenta para el bloqueo del primero (5 fallos desde .5 bloquean a .5; login correcto desde .6 sigue funcionando).
La IP guardada en RegistroAuditoria del login fallido coincide con la de axes.

Archivos del commit: nginx/nginx.conf, backend/core/utils.py, backend/core/tests.py, backend/accounts/signals.py, backend/accounts/tests.py, backend/administracion/signals.py, backend/sysadmin/settings/base.py. Commit propuesto: fix(seguridad): IP real del cliente para axes y auditoría (axes sin ipware), X-Forwarded-For no falsificable

B6 — Formulario público de soporte: límite que no se evade (hallazgo M3)

Cambios exactos:

soporte/views.py, en reportar_publico, justo después de la validación del cooldown por sesión existente y antes de crear el ticket (también en el camino POST con form.is_valid()), añade límite global compartido entre workers por BD:
python
   def _limite_global_alcanzado():
       maximo = getattr(settings, "SOPORTE_REPORTE_PUBLICO_MAX_POR_MINUTO", 0)
       if not maximo:
           return False
       desde = timezone.now() - timedelta(minutes=1)
       return Ticket.objects.filter(solicitante__isnull=True, fecha_creacion__gte=desde).count() >= maximo

Si es True: messages.error(request, "Hay muchos reportes en este momento. Espera un minuto e inténtalo de nuevo, o contacta directamente a Sistemas.") y renderiza soporte/reporte_publico.html con el form (mismo patrón del cooldown). Verifica que Ticket tiene fecha_creacion; si no, usa el campo real. 2. Settings: base.py y production.py: SOPORTE_REPORTE_PUBLICO_MAX_POR_MINUTO = int(os.environ.get("SOPORTE_REPORTE_PUBLICO_MAX_POR_MINUTO", "10")); local.py: = 0 (igual que el cooldown). Añade la variable a .env.example con comentario. 3. nginx/nginx.conf: al principio del archivo (fuera de server, contexto http) añade

nginx
   # Limita solo los POST al formulario público (6/min por IP, ráfaga 5).
   map $request_method $soporte_limit_key {
       default "";
       POST    $binary_remote_addr;
   }
   limit_req_zone $soporte_limit_key zone=soporte_publico:10m rate=6r/m;

y dentro del server HTTPS, antes de location /:

nginx
   location = /soporte/reportar-publico/ {
       limit_req zone=soporte_publico burst=5 nodelay;
       limit_req_status 429;
       proxy_pass http://django_backend;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $remote_addr;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_redirect off;
   }
Tests (soporte/tests.py, override_settings(SOPORTE_REPORTE_PUBLICO_MAX_POR_MINUTO=2, SOPORTE_REPORTE_PUBLICO_COOLDOWN_SEGUNDOS=0)): con clientes distintos y sin cookies (un Client() nuevo por envío), los 2 primeros POST válidos crean ticket y el 3º no crea ticket y muestra el mensaje; con el setting en 0 no limita; el honeypot sigue sin crear ticket.

Archivos del commit: backend/soporte/views.py, backend/soporte/tests.py, backend/sysadmin/settings/base.py, …/production.py, …/local.py, nginx/nginx.conf, .env.example. Commit propuesto: fix(soporte): límite global por minuto en formulario público (BD) + limit_req en nginx

B7 — Clave del vault y backup (hallazgos M4 y M6)
B7a — Aviso en check --deploy si falta PASSWORDS_ENCRYPTION_KEY

NO lances excepción ni cambies build_fernet(): producción podría estar usando hoy la clave derivada de SECRET_KEY; exigirla o cambiarla dejaría ilegibles las contraseñas ya cifradas.

backend/core/checks.py (nuevo):
python
   from django.conf import settings
   from django.core.checks import Tags, Warning, register

   @register(Tags.security, deploy=True)
   def clave_vault_check(app_configs, **kwargs):
       if getattr(settings, "PASSWORDS_ENCRYPTION_KEY", ""):
           return []
       return [Warning(
           "PASSWORDS_ENCRYPTION_KEY no está definida: la clave del vault se deriva de SECRET_KEY.",
           hint="Rotar SECRET_KEY dejaría ilegibles las contraseñas cifradas. Ver procedimiento en AGENT_RUNBOOK.md.",
           id="sysadmin.W001",
       )]
Importarlo desde core/apps.py (ready(): from . import checks  # noqa: F401); si CoreConfig no existe o no está referenciada en INSTALLED_APPS (hoy es 'core'), importa core.checks en core/__init__.py… elige lo mínimo que haga que python manage.py check --deploy lo muestre y repórtalo.
Test en core/tests.py: con override_settings(PASSWORDS_ENCRYPTION_KEY="") la función devuelve 1 warning sysadmin.W001; con una clave Fernet válida devuelve [].
AGENT_RUNBOOK.md: nueva sección corta "Rotar/definir PASSWORDS_ENCRYPTION_KEY" que explique: si producción hoy NO la tiene definida, NO basta con agregarla (rompe lo ya cifrado); procedimiento seguro = script de re-cifrado (descifrar con clave derivada → cifrar con la nueva) ejecutado en ventana con backup previo. No escribas ese script ahora; solo documenta el riesgo y que está pendiente.
B7b — deploy/backup.sh robusto (reemplaza el heredoc de setup_server.sh)

Crea deploy/backup.sh (archivo real, LF, UTF-8 sin BOM, ejecutable) con este comportamiento exacto:

#!/usr/bin/env bash + set -euo pipefail.
Config externa: source /opt/sysadmin/backups/backup.conf si existe (variables NAS_IP, NAS_USER, NAS_PATH). Sin valores por defecto con XXX.
Directorios: BACKUP_DIR=/opt/sysadmin/backups, SECURE_DIR=$BACKUP_DIR/secure (mkdir -p, chmod 700), log a stdout.
trap 'rm -f "$BACKUP_DIR/db_dump.sql"' EXIT (el dump en claro se borra siempre, incluso si falla).
Dump: docker exec sysadmin_db pg_dumpall -U sysadmin_user > "$BACKUP_DIR/db_dump.sql"; luego test -s "$BACKUP_DIR/db_dump.sql" (falla si está vacío).
Archivo datos (DB + media), sin .env: tar -czf "$BACKUP_DIR/sysadmin_backup_${FECHA}.tar.gz" -C "$BACKUP_DIR" db_dump.sql -C /opt/sysadmin/app/backend media (sin 2>/dev/null, sin || true); después tar -tzf … >/dev/null para validar integridad.
Archivo secretos aparte, solo local: tar -czf "$SECURE_DIR/env_${FECHA}.tar.gz" -C /opt/sysadmin/app .env + chmod 600. Nunca se envía al NAS (rsync con --exclude 'secure/').
NAS: si NAS_IP/NAS_USER/NAS_PATH no están definidos o NAS_IP contiene X, imprime AVISO: NAS no configurado, backup solo local y termina exit 0 tras el paso local. Si están definidos: rsync -az --exclude 'secure/' --exclude 'backup.log' "$BACKUP_DIR/" "${NAS_USER}@${NAS_IP}:${NAS_PATH}/" sin --delete (la retención en el NAS no debe reflejar la limpieza local).
Retención local: find "$BACKUP_DIR" -maxdepth 1 -name 'sysadmin_backup_*.tar.gz' -mtime +7 -delete y lo mismo para $SECURE_DIR/env_*.tar.gz con -mtime +30.
Comentario de cabecera con el procedimiento de restauración (descomprimir; docker exec -i sysadmin_db psql -U sysadmin_user -d postgres < db_dump.sql; copiar media/), marcado "PROBAR en un entorno de prueba".
setup_server.sh: reemplaza todo el heredoc cat > /opt/sysadmin/backups/backup.sh << 'BACKUP_SCRIPT' … BACKUP_SCRIPT por: copiar /opt/sysadmin/app/deploy/backup.sh a /opt/sysadmin/backups/backup.sh si existe (install -m 750), y si no existe imprimir aviso de copiarlo manualmente tras sincronizar el código; conserva la línea del cron y el chmod. Actualiza el mensaje final para indicar que la configuración del NAS va en /opt/sysadmin/backups/backup.conf.
Valida sintaxis: bash -n deploy/backup.sh (WSL/Git Bash) y, si tienes shellcheck, pásalo y reporta.

Archivos del commit: backend/core/checks.py, backend/core/apps.py (o el que corresponda), backend/core/tests.py, AGENT_RUNBOOK.md, deploy/backup.sh, setup_server.sh. Commit propuesto: fix(backup+vault): backup.sh sin fallos silenciosos ni .env al NAS; aviso W001 por clave del vault derivada

— FIN FASE 2: resumen y espera —

FASE 3
B8 — Quitar dependencias de CDN (hallazgo M5)

Referencias a eliminar (verificadas):

templates/base.html:9-13,19,155 → bootstrap 5.3.2 (css + bundle js), bootstrap-icons 1.11.1, Google Fonts (JetBrains Mono 400/600; Sora 300/400/600/700), htmx 1.9.6 (unpkg).
inventario/templates/inventario/qr_publico.html:8-10 → Google Fonts Sora 400/500/600/700.
soporte/templates/soporte/reporte_publico.html:8-10 y reporte_publico_exito.html:8-10 → bootstrap css, bootstrap-icons css, Sora.
mantenimiento/templates/mantenimiento/calendario.html:24,28 → fullcalendar 6.1.10 (css + js).

Procedimiento:

En un directorio temporal (fuera del repo) baja los paquetes con versión exacta: npm pack bootstrap@5.3.2 bootstrap-icons@1.11.1 htmx.org@1.9.6 fullcalendar@6.1.10 @fontsource/sora @fontsource/jetbrains-mono y extrae. Anota las versiones de fontsource usadas.
Copia a backend/static/vendor/ (estructura exacta):
bootstrap/css/bootstrap.min.css, bootstrap/js/bootstrap.bundle.min.js (de dist/), bootstrap/LICENSE
bootstrap-icons/font/bootstrap-icons.css + toda la carpeta fonts/ junto a él (el CSS la referencia con ruta relativa ./fonts/...), bootstrap-icons/LICENSE
htmx/htmx.min.js (de dist/htmx.min.js), htmx/LICENSE
fullcalendar/index.global.min.js (si el paquete trae CSS aparte, cópialo; si no existe el CSS que hoy se enlaza, elimina esa línea <link> y reporta)
fonts/sora-<peso>-latin.woff2 (pesos 300,400,500,600,700) y fonts/jetbrains-mono-<peso>-latin.woff2 (400,600), solo subconjunto latin (cubre á é í ó ú ñ ü ¿ ¡), más fonts/fonts.css con los @font-face (font-display: swap, font-family: 'Sora' / 'JetBrains Mono', rutas relativas ./).
En cada plantilla: añade {% load static %} si falta y reemplaza cada URL externa por {% static 'vendor/...' %} equivalente; elimina los <link rel="preconnect"> a Google. No cambies nada más del HTML/CSS.
Test nuevo core/tests.py::test_plantillas_sin_cdn_externos: recorre todos los *.html bajo backend/templates y backend/*/templates y falla si encuentra cdn.jsdelivr.net, unpkg.com, googleapis.com, gstatic.com o cdnjs. Debe pasar al final.
Verificación manual con internet desconectado (o bloqueando esos dominios en el navegador): login, dashboard, una lista con HTMX (búsqueda en inventario), calendario de mantenimiento, formulario público de soporte y página QR público → todo con estilos, iconos, fuentes y funcionando. Reporta cada pantalla OK/FALLA.
python manage.py collectstatic --noinput --dry-run no debe dar error y debe listar vendor/.

Archivos del commit: backend/static/vendor/**, las 5 plantillas, backend/core/tests.py. Commit propuesto: fix(ui): vendorizar bootstrap, icons, htmx, fullcalendar y fuentes; sin CDN externos

B9 — Endurecer nginx para estáticos y TLS (hallazgo L5)

En nginx/nginx.conf (cumulativo con B2/B5/B6, no los pises):

location /static/: añade add_header X-Content-Type-Options "nosniff" always;, add_header Cache-Control "public, max-age=604800";
Quita includeSubDomains del header HSTS (el sitio se sirve por IP): queda add_header Strict-Transport-Security "max-age=31536000" always;
En el server HTTPS, añade ssl_protocols TLSv1.2 TLSv1.3; y, antes de las locations, gzip on; gzip_types text/css application/javascript application/json image/svg+xml; gzip_min_length 1024;
No añadas CSP (las plantillas usan scripts/estilos inline; sería un cambio aparte). No cambies puertos ni el redirect :6060.
Valida sintaxis: docker run --rm -v "${PWD}/nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.25-alpine nginx -t (fallará solo por falta de certificados; si es así crea certs temporales con openssl en un directorio temporal y móntalos en /etc/nginx/certs, y reporta que nginx -t da syntax is ok). Alternativa: reporta que no pudiste validar.

Archivos del commit: nginx/nginx.conf. Commit propuesto: chore(nginx): nosniff y cache en estáticos, TLS 1.2+, gzip, HSTS sin includeSubDomains

B10 — gunicorn y contenedor (hallazgo M7, parte segura)
backend/entrypoint.sh: reemplaza la última línea por
bash
   exec gunicorn sysadmin.wsgi:application \
       --bind 0.0.0.0:8000 \
       --workers "${GUNICORN_WORKERS:-3}" \
       --timeout "${GUNICORN_TIMEOUT:-120}" \
       --access-logfile - \
       --error-logfile -

(Verificado en la auditoría: no hay CACHES/django.core.cache ni polling; varios workers es seguro. Los PDF WeasyPrint largos ya no matan al único worker.) 2. backend/.dockerignore (nuevo): __pycache__/, *.pyc, .ruff_cache/, .coverage, db.sqlite3, *.sqlite3, media/, staticfiles/, .git, .env, *.md. 3. .gitignore (raíz): añade .ruff_cache/ y .coverage. 4. .env.example: añade comentadas # GUNICORN_WORKERS=3 y # GUNICORN_TIMEOUT=120. 5. NO HACER (riesgo de romper producción; queda para otro prompt): correr el contenedor como usuario no-root (USER), quitar el bind mount ./backend:/app, cambiar permisos 777 de media. 6. bash -n backend/entrypoint.sh debe pasar; verifica que el archivo conserva fin de línea LF (git ls-files --eol backend/entrypoint.sh → w/lf); si es CRLF, conviértelo (rompe el contenedor).

Archivos del commit: backend/entrypoint.sh, backend/.dockerignore, .gitignore, .env.example. Commit propuesto: chore(docker): gunicorn con workers/timeout/logs configurables y .dockerignore

— FIN FASE 3: resumen y espera —

FASE 4
B11 — Lint, BOM, mark_safe, imports muertos, documentación (hallazgos L1, L4, L8, L9)

Este bloque toca muchos archivos: se hace al final para no generar conflictos con los anteriores. Commits separados (11a código, 11b docs).

B11a — Configuración y limpieza de ruff
Crea backend/ruff.toml:
toml
   target-version = "py311"
   extend-exclude = ["**/migrations/*"]

   [lint]
   select = ["E", "F", "W", "B", "DJ"]
   ignore = ["E501", "DJ012"]

No adoptes ruff format (generaría un diff gigante). 2. Línea base medida en la auditoría con esta config: 201 hallazgos (102 W293, 41 W292, 23 E741, 21 F401, 4 B904, 4 F841, 3 B007, 2 F811, 1 F541). Objetivo: ruff check . → 0. 3. Orden de trabajo:

ruff check . --select W293,W292 --fix --unsafe-fixes (solo espacios/fin de archivo) y comprueba que git diff -w --stat no muestra cambios de contenido real.
ruff check . --select F401 --fix y revisa el diff: excepción — yule/admin.py importa buscar_posibles_matches sin uso; confirma con grep -rn "buscar_posibles_matches" backend que ningún otro módulo lo importa desde yule.admin antes de quitarlo.
E741 (l) en licencias/views.py (líneas 26-40, 64, 77-79, 238-243): renombrar la variable l a lic (o licencia) solo dentro de esas expresiones/lambdas/comprensiones, sin cambiar lógica.
B904 (documentos/views.py:104,115, yule/client.py:238,334): añadir from None (o from exc si ya se captura como exc) en el raise dentro del except.
F841/B007/F541: eliminar la variable sin uso o renombrar la de bucle a _ (limpiar_historial.py:119 dirs→_dirs, reports/views.py:737 row_idx→_row_idx, soporte/views.py:420 idx→_idx); en tests quitar solo la asignación sin uso, conservando la llamada.
F811: inventario/tests.py:232 define dos veces SoftwareInventarioBase (la segunda oculta la primera → posibles tests que nunca corren). No borres nada a ciegas: compara ambas clases, reporta si las subclases heredan de la que no corresponde y propón la corrección; aplica solo si es inequívoca (renombrar la segunda y ajustar sus subclases) y verifica que el conteo de tests sube o se mantiene explicable. usuarios/views.py:15 import openpyxl duplicado → quitar el repetido.
reports/views.py:564: reemplaza mark_safe(f'<span class="badge {activo.estado}">{raw}</span>') por format_html('<span class="badge {}">{}</span>', activo.estado, raw) (import from django.utils.html import format_html; quitar mark_safe si queda sin uso). Verifica que el export PDF de inventario con columna "estado" sigue igual (test existente + comparar HTML).
BOM: patch_ocs_server.sh (raíz): reescribir sin BOM (#!/usr/bin/env bash debe ser el primer byte), conservando LF. Verifica head -c3 ≠ EF BB BF. (accounts/signals.py ya se hizo en B5.)
Criterio: ruff check backend → All checks passed!; suite completa sin regresiones (mismo o mayor número de tests que antes del bloque).

Archivos del commit 11a: backend/ruff.toml y los .py tocados (lista exacta con git diff --name-only), patch_ocs_server.sh. Commit propuesto 11a: style: ruff (E,F,W,B,DJ) a cero, imports muertos, format_html, sin BOM

B11b — Documentación
Crea docs/informes/ y mueve con git mv los informes de la raíz: INFORME_ARQUITECTURA_2026-09-28.md, INFORME_OCS_YULE_2026-09-25.md, INFORME_TECNICO_OCS_YULE_2026-09-28.md, y añade AUDITORIA_SYSADMIN_2026-10-14.md (Bairon te la entrega). No muevas README.md, AGENTS.md, AGENT_RUNBOOK.md, CHECKLIST_DEPLOY.md, GUIA_DEPLOY_PASO_A_PASO.md, OCS_INVENTORY_SETUP.md, MANUAL_AGENTE_OCS.md, ETIQUETAS_IMPRESION.md, FASES.md, SYSADMIN_HANDOFF.md.
grep -rn "INFORME_" --include=*.md . y actualiza los enlaces rotos por el movimiento.
AGENTS.md: añade sección "Cambios de la auditoría 2026-10-14" con una línea por bloque aplicado (B1–B11) y las decisiones: timeout configurable SESSION_COOKIE_AGE; /media/ pasa por Django (core.views.media_protegido, prefijos en MEDIA_PERMISOS: todo campo de upload nuevo debe registrarse ahí, hay un test que lo exige); get_client_ip; límite global de tickets públicos; backup.sh + backup.conf; vendor local de CDN; ruff obligatorio. Commit propuesto 11b: docs: informes a docs/informes y registro de cambios de la auditoría
B12 — CI (hallazgo M8)

Edita .github/workflows/ci.yml (conserva los pasos actuales) para quedar con:

Job lint: pip install ruff → ruff check backend.
Job test (el existente) + pasos: python manage.py makemigrations --check --dry-run; python manage.py check ; python manage.py check --deploy --fail-level ERROR (con env: DJANGO_SETTINGS_MODULE: sysadmin.settings.production, SECRET_KEY de CI, POSTGRES_DB/USER/PASSWORD dummy, ALLOWED_HOSTS: localhost — check no conecta a la BD); tests con cobertura: pip install coverage → coverage run --source=. --omit='*/tests.py,*/migrations/*,manage.py' manage.py test --noinput → coverage report --fail-under=70.
Job test-postgres con services: postgres: image: postgres:15-alpine (env POSTGRES_DB/USER/PASSWORD, health-cmd pg_isready), env POSTGRES_DB=ci_db POSTGRES_USER=ci POSTGRES_PASSWORD=ci DB_HOST=localhost DB_PORT=5432 DJANGO_SETTINGS_MODULE=sysadmin.settings.local, mismos tests. continue-on-error: true por ahora (nunca se corrió contra Postgres).
Job audit (continue-on-error: true): pip install pip-audit → pip-audit -r backend/requirements.txt --no-deps --disable-pip.
Verificación local obligatoria de PostgreSQL (Bairon tiene Docker Desktop):
powershell
   docker run -d --name pg_ci -e POSTGRES_DB=ci_db -e POSTGRES_USER=ci -e POSTGRES_PASSWORD=ci -p 55432:5432 postgres:15-alpine
   $env:POSTGRES_DB="ci_db"; $env:POSTGRES_USER="ci"; $env:POSTGRES_PASSWORD="ci"; $env:DB_HOST="localhost"; $env:DB_PORT="55432"
   python manage.py test --noinput 2>&1 | Out-File -Encoding utf8 "$env:TEMP\pg_tests.txt"; Get-Content "$env:TEMP\pg_tests.txt" -Tail 40
   docker rm -f pg_ci

Pega el resultado completo. Si hay fallas propias de PostgreSQL, no las arregles en este bloque: lista cada una (test, error, causa probable). Esto cubre también la importación de usuarios/activos contra Postgres real. 6. Valida el YAML (python -c "import yaml,sys;yaml.safe_load(open('.github/workflows/ci.yml'))").

Archivos del commit: .github/workflows/ci.yml. Commit propuesto: ci: lint, makemigrations --check, check --deploy, cobertura, job PostgreSQL y pip-audit

B13 — Tests mínimos para comandos de management con 0 % de cobertura (hallazgo L3)

Comandos: core/management/commands/limpiar_historial.py, yule/management/commands/sync_ocs.py, notificaciones/management/commands/generar_notificaciones_mantenimiento.py, notificaciones/management/commands/enviar_notificaciones_email.py.

Lee cada comando y sus argumentos. En <app>/tests.py (o tests_commands.py si el archivo ya es muy grande) añade con call_command(..., stdout=StringIO()):
limpiar_historial: primero lee si tiene --dry-run/similar. Test A: con datos antiguos y modo simulación → no borra nada. Test B: ejecución real con registros viejos/nuevos → borra solo los que superan la antigüedad definida por el comando y respeta lo que no debe tocar (media huérfana: usa override_settings(MEDIA_ROOT=tmpdir)). Antes de escribir los tests, resume en el reporte qué hace exactamente el comando (qué modelos/archivos borra) para que Bairon lo valide.
sync_ocs: con patch del cliente OCS (mismo estilo que yule/tests.py) → corre sin error y reporta contadores; con cliente que lanza excepción → sale con mensaje, no deja trazas sin capturar.
generar_notificaciones_mantenimiento y enviar_notificaciones_email: corren sin datos (no fallan) y con un caso mínimo (1 orden próxima / 1 email en cola con EMAIL_BACKEND locmem) producen el efecto esperado (notificación creada / enviado=True).
No modifiques el código de los comandos. Si algo es imposible de testear sin cambiarlo, repórtalo.
Cobertura: corre coverage como en B12 y reporta la cobertura de esos 4 archivos (objetivo > 70 % cada uno).

Archivos del commit: los tests*.py tocados. Commit propuesto: test: cobertura de comandos de management (limpiar_historial, sync_ocs, notificaciones)

FUERA DE ALCANCE (no tocar; se decide aparte)
Subir a Django 5.2 LTS y WeasyPrint 70 (solo se prueba WeasyPrint en B3b).
Refactor de funciones complejas (inventario_pdf CC 34, aplicar_reporte CC 32, etc.) y mover helpers Excel de reports.views.
Contenedor como no-root, quitar bind mount, permisos 777.
Token en vez de pk en QR público; CSP en nginx.
Script de re-cifrado del vault.
Cualquier acción sobre el servidor (deploy, cron, NAS).
ENTREGA FINAL (después de B13)

Reporte único: tabla hallazgo → bloque → commit → estado, conteo final de tests (esperado ≥ 407 + los nuevos), salida de ruff check backend, cobertura total, y lista de pendientes/diferencias detectadas. No hagas push; Bairon lo hace tras revisar.  