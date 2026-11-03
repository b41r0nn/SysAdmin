"""Política de seguridad del login, leída de la base de datos.

Lo que antes estaba fijo en los settings —el límite de intentos de axes, la
duración del bloqueo, la longitud mínima de la contraseña y el vencimiento de
la sesión— se lee aquí de ``ConfiguracionSistema``.

Dos reglas gobiernan este módulo y no son de estilo:

1. **Se lee en vivo, sin caché.** Cuesta una consulta por petición autenticada
   y es un coste asumido: ``SESSION_SAVE_EVERY_REQUEST`` ya escribe la sesión
   en cada petición, así que un SELECT más no mueve la aguja. En cambio una
   caché sí cambiaría el comportamiento, porque los cambios masivos
   (``queryset.update()``) no disparan señales y la política quedaría vieja.

2. **Ninguna lectura puede tumbar el login.** ``get_config()`` es un
   ``get_or_create``: escribe, y revienta si la tabla todavía no existe (base
   nueva, ``migrate`` a medias). Cada lectura va envuelta en
   ``try/except DatabaseError`` y cae a un valor de respaldo, porque un candado
   sin llave es peor que un candado flojo.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import MinimumLengthValidator
from django.db import DatabaseError

from .models import ConfiguracionSistema

logger = logging.getLogger(__name__)

# Valores de respaldo cuando la base de datos no responde. NO pueden salir de
# settings.AXES_FAILURE_LIMIT ni de settings.AXES_COOLOFF_TIME porque esos dos
# settings son, desde este cambio, la ruta con puntos de las funciones de aquí:
# leerlos devolvería un str. Coinciden con los defaults de los campos del
# modelo y hay una prueba que lo exige
# (test_los_respaldos_coinciden_con_los_defaults_del_modelo).
INTENTOS_POR_DEFECTO = 5
HORAS_DE_BLOQUEO_POR_DEFECTO = 1

# Traducción de «0 horas» (= el bloqueo no caduca). axes expresa eso con
# AXES_COOLOFF_TIME = None, pero ese atajo no está disponible aquí: con la ruta
# con puntos el setting nunca es None, así que las guardas
# `if settings.AXES_COOLOFF_TIME is None` de axes/handlers/database.py:383 y
# :404 no se activan y axes/attempts.py:18-21 lanza TypeError, es decir un 500
# en CADA intento de login y para todo el mundo. Un siglo de bloqueo da la
# misma política (no caduca en la vida de la instalación) sin romper nada.
BLOQUEO_SIN_CADUCIDAD = timedelta(days=365 * 100)


def limite_de_intentos(request=None, credentials=None):
    """Intentos fallidos que axes tolera antes de bloquear.

    La firma es la que espera ``AXES_FAILURE_LIMIT`` cuando es una ruta con
    puntos: axes la llama como ``funcion(request, credentials)``
    (``axes/helpers.py:446-455``).
    """
    try:
        return ConfiguracionSistema.get_config().intentos_antes_de_bloquear
    except DatabaseError:
        logger.warning(
            "No se pudo leer el límite de intentos de la configuración; "
            "se usa el respaldo de %s.", INTENTOS_POR_DEFECTO,
        )
        return INTENTOS_POR_DEFECTO


def tiempo_de_bloqueo(request=None):
    """Cuánto dura el bloqueo de axes.

    La firma es la que espera ``AXES_COOLOFF_TIME`` cuando es una ruta con
    puntos: axes la llama como ``funcion(request)`` (``axes/helpers.py:52-74``).

    Nunca devuelve ``None``, aunque sea lo que axes documenta como «sin bloqueo
    temporal»: ver ``BLOQUEO_SIN_CADUCIDAD``.
    """
    try:
        horas = ConfiguracionSistema.get_config().horas_de_bloqueo
    except DatabaseError:
        logger.warning(
            "No se pudieron leer las horas de bloqueo de la configuración; "
            "se usa el respaldo de %s.", HORAS_DE_BLOQUEO_POR_DEFECTO,
        )
        horas = HORAS_DE_BLOQUEO_POR_DEFECTO
    if not horas:
        return BLOQUEO_SIN_CADUCIDAD
    return timedelta(hours=horas)


def minutos_de_sesion():
    """Minutos de inactividad antes de cerrar la sesión."""
    try:
        return ConfiguracionSistema.get_config().sesion_minutos
    except DatabaseError:
        respaldo = settings.SESSION_COOKIE_AGE // 60
        logger.warning(
            "No se pudieron leer los minutos de sesión de la configuración; "
            "se usa el respaldo de %s.", respaldo,
        )
        return respaldo


class LongitudMinimaConfigurable(MinimumLengthValidator):
    """``MinimumLengthValidator`` con la longitud mínima en base de datos.

    Django instancia los validadores de ``AUTH_PASSWORD_VALIDATORS`` una sola
    vez, así que la longitud se resuelve en cada ``validate()`` y en cada
    ``get_help_text()``: leerla en ``__init__`` congelaría el valor del
    arranque y un cambio en la pantalla no se aplicaría hasta reiniciar.

    El respaldo es ``self.min_length``, que viene de las ``OPTIONS`` del
    validador en los settings.
    """

    def longitud_minima(self):
        try:
            return ConfiguracionSistema.get_config().longitud_minima_password
        except DatabaseError:
            logger.warning(
                "No se pudo leer la longitud mínima de contraseña de la "
                "configuración; se usa el respaldo de %s.", self.min_length,
            )
            return self.min_length

    def validate(self, password, user=None):
        # Se delega en una instancia nueva en vez de reasignar self.min_length:
        # el validador es compartido entre peticiones y mutarlo no es seguro
        # con varios hilos. Así además el mensaje de error sigue siendo el de
        # Django, ya traducido.
        MinimumLengthValidator(self.longitud_minima()).validate(password, user)

    def get_help_text(self):
        return MinimumLengthValidator(self.longitud_minima()).get_help_text()
