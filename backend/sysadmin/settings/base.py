"""Settings comunes. No se usa directamente: ver local.py y production.py."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# local.py genera una clave temporal si falta; production.py exige que exista.
SECRET_KEY = os.environ.get('SECRET_KEY', '')

# Clave Fernet del vault. Si falta se deriva de SECRET_KEY (ver passwords.crypto
# y el check sysadmin.W001).
PASSWORDS_ENCRYPTION_KEY = os.environ.get('PASSWORDS_ENCRYPTION_KEY', '')

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

# Cada entorno define su base de datos (local.py: SQLite o PostgreSQL;
# production.py: PostgreSQL obligatorio).
DATABASES = {}

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
# Timeout por INACTIVIDAD (segundos). SAVE_EVERY_REQUEST renueva la expiración
# en cada petición; sin él, el tiempo cuenta desde el login y no desde la última actividad.
SESSION_COOKIE_AGE = int(os.environ.get('SESSION_COOKIE_AGE', '1800'))
SESSION_SAVE_EVERY_REQUEST = True
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
AXES_CLIENT_IP_CALLABLE = "core.utils.get_client_ip"

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
MEDIA_ACCEL_REDIRECT = False

OCS_BASE_URL = os.environ.get('OCS_BASE_URL', '').rstrip('/')
OCS_USER = os.environ.get('OCS_USER', '')
OCS_TOKEN = os.environ.get('OCS_TOKEN', '')
OCS_VERIFY_SSL = os.environ.get('OCS_VERIFY_SSL', 'True') == 'True'

# CSRF / Security Configuration
# Leer flags de seguridad desde el entorno. Por defecto activamos valores seguros
# cuando DEBUG=False (entorno de producción), y valores permissivos en desarrollo.

# Headers de seguridad (nativos Django, activos siempre)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'

# Por defecto desactivados para no romper login en LAN sin HTTPS.
# Activar explícitamente en producción con HTTPS mediante variables de entorno.
SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", False)

# Django corre detrás de nginx, que termina el TLS y reenvía el esquema real
# mediante X-Forwarded-Proto. Sin SECURE_PROXY_SSL_HEADER, Django ignora ese
# header y con SECURE_SSL_REDIRECT=True entra en redirect loop (nunca "ve" que
# la petición ya es HTTPS por parte del proxy).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = _env_bool("CSRF_COOKIE_SECURE", False)

# HSTS (usar con HTTPS en producción)
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000' if not DEBUG else '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', not DEBUG)
SECURE_HSTS_PRELOAD = _env_bool('SECURE_HSTS_PRELOAD', not DEBUG)

# Orígenes confiables para CSRF: lista separada por comas en TRUSTED_ORIGINS.
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get('TRUSTED_ORIGINS', '').split(',') if o.strip()
]

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
