"""Settings para producción (PostgreSQL, HTTPS forzado)."""
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY no está configurado en el entorno")

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# PostgreSQL obligatorio en producción.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB"),
        "USER": os.environ.get("POSTGRES_USER"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD"),
        "HOST": os.environ.get("DB_HOST", "db"),
        "PORT": os.environ.get("DB_PORT", 5432),
    }
}

# HTTPS forzado (valores por defecto seguros; se pueden desactivar vía .env).
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)  # noqa: F405
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)  # noqa: F405
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)  # noqa: F405

# HSTS lo envía nginx para todo el tráfico; evitamos duplicarlo en
# respuestas dinámicas de Django.
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Cooldown para evitar spam en formulario público de tickets.
SOPORTE_REPORTE_PUBLICO_COOLDOWN_SEGUNDOS = int(
    os.environ.get("SOPORTE_REPORTE_PUBLICO_COOLDOWN_SEGUNDOS", "60")
)

_origenes = os.environ.get("TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = (
    [o.strip() for o in _origenes.split(",") if o.strip()]
    if _origenes
    else ["https://192.168.1.250:6060"]
)
