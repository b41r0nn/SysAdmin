"""Test E2E de importación de usuarios: parsear xlsx -> preview -> confirm."""
import io
import os
import sys
import types
import django
from django.conf import settings

# Stub de weasyprint: requiere GTK que no existe en Windows. El test no toca PDFs.
sys.modules.setdefault("weasyprint", types.ModuleType("weasyprint"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

settings.configure(
    DEBUG=True,
    SECRET_KEY="test-secret",
    BASE_DIR=BASE_DIR,
    ROOT_URLCONF="sysadmin.urls",
    INSTALLED_APPS=[
        "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
        "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
        "accounts", "core", "usuarios", "inventario", "reports",
        "mantenimiento", "documentos", "yule", "passwords",
    ],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    TEMPLATES=[{
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.request",
            "django.contrib.messages.context_processors.messages",
        ]},
    }],
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ],
    STATIC_URL="/static/",
    USE_TZ=True,
    ALLOWED_HOSTS=["testserver"],
    LOGIN_URL="/accounts/login/",
)
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from django.core.management import call_command
from usuarios.models import Usuario
from usuarios.views import _reordenar_nombre, _parsear_excel_usuarios

call_command("migrate", run_syncdb=True, verbosity=0)
User.objects.create_superuser("admin", "admin@test.com", "pass")

import openpyxl
from openpyxl import Workbook

# ─── Unit: reordenar nombre ────────────────────────────────────────────────
assert _reordenar_nombre("CALLE RIVERA BAIRON NICOLAS") == "Bairon Nicolas Calle Rivera"
assert _reordenar_nombre("LOPEZ MARTA") == "Lopez Marta"      # 2 palabras: caso ambiguo, se deja tal cual
assert _reordenar_nombre("RUIZ") == "Ruiz"                    # 1 palabra: sin cambio
assert _reordenar_nombre("  gomez  perez   JUAN  ") == "Juan Gomez Perez"  # espacios extra
print("OK unit — _reordenar_nombre")

# ─── Unit: parser con xlsx en memoria ──────────────────────────────────────
wb = Workbook()
ws = wb.active
ws.append(["Nombre Completo", "Identificación", "Cargo", "Área", "Número Celular", "Correo Corporativo", "Columna Rara"])
ws.append(["CALLE RIVERA BAIRON NICOLAS", "100200300", "Analista", "Sistemas", "3001234567", "bcalle@redihos.com", "x"])
ws.append(["LOPEZ GOMEZ MARTA", "200300400", "Contadora", "Finanzas", None, "mlopez@redihos.com", "x"])
ws.append(["SIN DOCUMENTO PRUEBA", None, "Practicante", "Talento", "3100000000", None, "x"])
ws.append([None, None, None, None, None, None, None])  # fila vacía -> se omite
stream = io.BytesIO()
wb.save(stream)
stream.seek(0)
stream.name = "prueba_usuarios.xlsx"  # Django test client usa file.name como nombre del upload

Usuario.objects.create(
    nombre_completo="Bairon Nicolas Calle Rivera", documento_identidad="100200300",
    cargo="Analista", area="Sistemas", correo="bcalle@redihos.com",
)

filas, advertencias = _parsear_excel_usuarios(stream)
assert len(filas) == 3, f"filas parseadas: {len(filas)}"
por_estado = {f["estado"] for f in filas}
assert "duplicado" in por_estado and "ok" in por_estado and "error_falta_documento" in por_estado
ok_row = [f for f in filas if f["estado"] == "ok"][0]
assert ok_row["datos"]["nombre_completo"] == "Marta Lopez Gomez"
assert ok_row["datos"]["telefono"] == ""     # celda None -> vacío, sin excepción
print("OK unit — _parsear_excel_usuarios (3 filas: ok/duplicado/error, vacía omitida)")

# ─── E2E: subir archivo real -> preview -> confirmar -> solo OK creados ────
c = Client()
c.force_login(User.objects.get(username="admin"))

stream.seek(0)
r = c.post("/usuarios/importar/", {"archivo": stream})
assert r.status_code == 200 and "Vista previa" in r.content.decode()
assert b"Marcar todos" not in r.content  # no es esa pantalla
print("OK e2e — preview renderizada")

r = c.post("/usuarios/importar/confirmar/", follow=True)
assert r.status_code == 200
creados = Usuario.objects.filter(estado="activo").count()
nuevos = Usuario.objects.exclude(documento_identidad="100200300")
assert nuevos.count() == 1, f"Se debía crear solo la fila OK, creados: {nuevos.count()}"
assert nuevos.first().nombre_completo == "Marta Lopez Gomez"
print("OK e2e — confirmación creó solo filas OK")

# ─── E2E: confirmar sin preview -> error y redirect ────────────────────────
r = c.post("/usuarios/importar/confirmar/")
assert r.status_code == 302
print("OK e2e — confirmar sin datos en sesión redirige")

# ─── Guard contra duplicados re-check (carrera entre preview y confirm) ────
stream.seek(0)
c.post("/usuarios/importar/", {"archivo": stream})
# no confirmar; crear a mano el documento ok y confirmar después
Usuario.objects.create(
    nombre_completo="Marta Lopez Gomez", documento_identidad="200300400",
    cargo="Contadora", area="Finanzas", correo="mlopez@redihos.com",
)
c.post("/usuarios/importar/confirmar/")
assert Usuario.objects.filter(documento_identidad="200300400").count() == 1, "No debió duplicarse"
print("OK e2e — doble verificación de duplicados en confirmación")

print("TODOS LOS TESTS PASARON")
