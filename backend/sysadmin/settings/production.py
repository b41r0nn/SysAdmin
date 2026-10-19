"""Settings para producción (PostgreSQL, HTTPS forzado)."""
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import _env_bool

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
SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = _env_bool("CSRF_COOKIE_SECURE", True)

# HSTS lo envía nginx para todo el tráfico; evitamos duplicarlo en
# respuestas dinámicas de Django.
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Cooldown para evitar spam en formulario público de tickets.
SOPORTE_REPORTE_PUBLICO_COOLDOWN_SEGUNDOS = int(
    os.environ.get("SOPORTE_REPORTE_PUBLICO_COOLDOWN_SEGUNDOS", "60")
)

# Caché compartida entre los workers de gunicorn: el cooldown por IP de soporte
# debe ser visible desde todos los procesos, pero el backend por defecto
# (LocMemCache) es por proceso. FileBasedCache usa el mismo directorio del
# contenedor para todos los workers.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": os.environ.get("DJANGO_CACHE_DIR", "/tmp/sysadmin_django_cache"),
    }
}

# En producción nginx sirve /media/ a través de X-Accel-Redirect (vista media_protegido).
MEDIA_ACCEL_REDIRECT = True

if not CSRF_TRUSTED_ORIGINS:  # noqa: F405
    raise ImproperlyConfigured(
        "TRUSTED_ORIGINS no está configurado (ej. https://192.168.1.250:6060)"
    )
