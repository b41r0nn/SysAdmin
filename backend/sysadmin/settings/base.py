import logging
import os
import secrets
from pathlib import Path

from decouple import config

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECRET_KEY: generar uno aleatorio si no existe (solo para desarrollo)
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(50)
    logger.critical(
        "SECRET_KEY not set in environment. Generated temporary key. "
        "Set SECRET_KEY in .env for production use."
    )

# PASSWORDS_ENCRYPTION_KEY: advertir si no está configurado
PASSWORDS_ENCRYPTION_KEY = os.environ.get('PASSWORDS_ENCRYPTION_KEY', '')
if not PASSWORDS_ENCRYPTION_KEY:
    logger.warning(
        "PASSWORDS_ENCRYPTION_KEY not set. Secrets will be derived from SECRET_KEY. "
        "Set PASSWORDS_ENCRYPTION_KEY in .env for production use."
    )

DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# URL base para los códigos QR. Si no se define, se usa la URL de la petición.
# Ejemplo: QR_BASE_URL=https://192.168.1.250:6060
QR_BASE_URL = os.environ.get('QR_BASE_URL', '')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'axes',

    # Custom apps
    'accounts',
    'core',
    'usuarios',
    'inventario',
    'mantenimiento',
    'passwords',
    'reports',
    'yule',
    'documentos',
    'administracion',
    'notificaciones',
    'soporte',
    'licencias',
    'prestamos',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'sysadmin.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'sysadmin.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# For local testing, we will just use sqlite3 to avoid postgres container issues if they don't want to run it, but the docker-compose expects postgres. Let's use SQLite if POSTGRES_DB is not set.
if os.environ.get('POSTGRES_DB'):
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB'),
        'USER': os.environ.get('POSTGRES_USER'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
        'HOST': os.environ.get('DB_HOST', 'db'),
        'PORT': os.environ.get('DB_PORT', 5432),
    }

AUTH_USER_MODEL = 'accounts.CustomUser'
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

# ─── Validadores de contraseña ────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 10,
        },
    },
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 28800  # 8h
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# ─── Seguridad del login ─────────────────────────────────────────────────────
# django-axes: rate limit / lockout por combinación usuario+IP
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # hora
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True

# Mensajes genéricos: no revelar si el usuario existe o no
AXES_IP_COOLOFF_MESSAGE = "Demasiados intentos fallidos. Intente de nuevo más tarde."
AXES_COOLOFF_MESSAGE = "Cuenta temporalmente bloqueada por demasiados intentos fallidos. Intente de nuevo más tarde."
AXES_LOCKOUT_MESSAGE = "Cuenta temporalmente bloqueada por demasiados intentos fallidos. Intente de nuevo más tarde."

LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

OCS_BASE_URL = os.environ.get('OCS_BASE_URL', '').rstrip('/')
OCS_USER = os.environ.get('OCS_USER', '')
OCS_TOKEN = os.environ.get('OCS_TOKEN', '')
OCS_VERIFY_SSL = os.environ.get('OCS_VERIFY_SSL', 'True') == 'True'

# CSRF / Security Configuration
# Leer flags de seguridad desde el entorno. Por defecto activamos valores seguros
# cuando DEBUG=False (entorno de producción), y valores permissivos en desarrollo.
def _env_bool(name, default):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes")

# Headers de seguridad (nativos Django, activos siempre)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'

# Por defecto desactivados para no romper login en LAN sin HTTPS.
# Activar explícitamente en producción con HTTPS mediante variables de entorno.
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)

# Django corre detrás de nginx, que termina el TLS y reenvía el esquema real
# mediante X-Forwarded-Proto. Sin SECURE_PROXY_SSL_HEADER, Django ignora ese
# header y con SECURE_SSL_REDIRECT=True entra en redirect loop (nunca "ve" que
# la petición ya es HTTPS por parte del proxy).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=False, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=False, cast=bool)

# HSTS (usar con HTTPS en producción)
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000' if not DEBUG else '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', not DEBUG)
SECURE_HSTS_PRELOAD = _env_bool('SECURE_HSTS_PRELOAD', not DEBUG)

# CSRF trusted origins: permitir localhost en desarrollo, configurable en producción
_default_csrf_origins = [
    'http://127.0.0.1:8000',
    'http://localhost:8000',
    'http://localhost:8001',
    'https://localhost:6060',
    'https://192.168.1.250:6060',
]
_env_csrf_origins = os.environ.get('TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = (
    [o.strip() for o in _env_csrf_origins.split(',') if o.strip()]
    if _env_csrf_origins
    else _default_csrf_origins
)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Cooldown entre tickets públicos (segundos). 0 = sin límite.
SOPORTE_REPORTE_PUBLICO_COOLDOWN_SEGUNDOS = int(
    os.environ.get('SOPORTE_REPORTE_PUBLICO_COOLDOWN_SEGUNDOS', '60')
)

# Logging de seguridad
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'security': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'security',
        },
    },
    'loggers': {
        'security': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
