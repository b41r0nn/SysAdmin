"""Política de seguridad del login, leída de la base de datos.

Lo que antes estaba fijo en los settings —el límite de intentos de axes, la
duración del bloqueo, la longitud mínima de la contraseña y el vencimiento de
la sesión— se lee aquí de ``ConfiguracionSistema``.

Tres reglas gobiernan este módulo y no son de estilo:

1. **Se lee en vivo, sin caché.** Cuesta una consulta por petición autenticada
   y es un coste asumido: ``SESSION_SAVE_EVERY_REQUEST`` ya escribe la sesión
   en cada petición, así que un SELECT más no mueve la aguja. En cambio una
   caché sí cambiaría el comportamiento, porque los cambios masivos
   (``queryset.update()``) no disparan señales y la política quedaría vieja.

2. **Ninguna lectura puede tumbar el login.** ``get_config()`` es un
   ``get_or_create``: escribe, y revienta si la tabla todavía no existe (base
   nueva, ``migrate`` a medias). Cada lectura va envuelta en
   ``try/except`` de ``django.db.Error`` —la base de la jerarquía, no
   ``DatabaseError``: el ``InterfaceError`` de psycopg («connection already
   closed») hereda de ``Error`` y **no** de ``DatabaseError``, y solo muerde en
   PostgreSQL, que es producción— y cae a un valor de respaldo, porque un
   candado sin llave es peor que un candado flojo.

3. **El resolvedor no se fía de la columna.** Cada valor se acota al rango
   aceptable *al leerlo* (``_acotado()``). Los validadores del campo no bastan:
   un ``queryset.update()`` o un ``UPDATE`` por SQL se los saltan igual que se
   saltan ``save()``, y un ``horas_de_bloqueo`` desbordante deja el login en 500
   para todo el mundo —``/admin/login/`` incluido— sin ninguna vuelta por la
   web. Es el mismo principio que ``accounts.permisos.modulos_activos()`` con
   ``MODULOS_ESENCIALES`` y que ``nivel_permiso`` con el superadministrador: la
   decisión sale de una constante de código, no del dato.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import MinimumLengthValidator
from django.db import Error as ErrorDeBaseDeDatos

from .models import (
    HORAS_DE_BLOQUEO_MAXIMO,
    HORAS_DE_BLOQUEO_MINIMO,
    INTENTOS_MAXIMO,
    INTENTOS_MINIMO,
    LONGITUD_MINIMA_MAXIMA,
    LONGITUD_MINIMA_MINIMA,
    SESION_MINUTOS_MAXIMO,
    SESION_MINUTOS_MINIMO,
    ConfiguracionSistema,
)

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


def _acotado(valor, minimo, maximo, etiqueta):
    """Acota al rango ``[minimo, maximo]`` un número que viene de la base.

    Es la capa que de verdad cierra el agujero del C1 y no se puede sustituir
    por los validadores del campo: ``queryset.update()`` y un ``UPDATE`` por SQL
    no corren ``save()`` ni ``full_clean()``, así que la fila puede contener
    cualquier entero positivo. Si se saliera del rango, se usa el tope más
    cercano y **queda traza en el log**, igual que ya hace este módulo cuando la
    base no responde: un valor silenciosamente distinto del guardado sería peor
    que el agujero.

    El ``None`` se trata aparte porque las columnas son ``NOT NULL`` hoy, pero
    un ``None`` llegando aquí daría un ``TypeError`` en la comparación, es decir
    el mismo 500 que se está evitando.
    """
    if valor is None or valor < minimo:
        logger.warning(
            "%s guardado fuera de rango (%r); se usa el mínimo de %s.",
            etiqueta, valor, minimo,
        )
        return minimo
    if valor > maximo:
        logger.warning(
            "%s guardado fuera de rango (%r); se usa el máximo de %s.",
            etiqueta, valor, maximo,
        )
        return maximo
    return valor


def limite_de_intentos(request=None, credentials=None):
    """Intentos fallidos que axes tolera antes de bloquear.

    La firma es la que espera ``AXES_FAILURE_LIMIT`` cuando es una ruta con
    puntos: axes la llama como ``funcion(request, credentials)``
    (``axes/helpers.py:446-455``).
    """
    try:
        guardado = ConfiguracionSistema.get_config().intentos_antes_de_bloquear
    except ErrorDeBaseDeDatos:
        logger.warning(
            "No se pudo leer el límite de intentos de la configuración; "
            "se usa el respaldo de %s.", INTENTOS_POR_DEFECTO,
        )
        return INTENTOS_POR_DEFECTO
    return _acotado(guardado, INTENTOS_MINIMO, INTENTOS_MAXIMO, "El límite de intentos")


def tiempo_de_bloqueo(request=None):
    """Cuánto dura el bloqueo de axes.

    La firma es la que espera ``AXES_COOLOFF_TIME`` cuando es una ruta con
    puntos: axes la llama como ``funcion(request)`` (``axes/helpers.py:52-74``).

    Nunca devuelve ``None``, aunque sea lo que axes documenta como «sin bloqueo
    temporal»: ver ``BLOQUEO_SIN_CADUCIDAD``.

    Y nunca devuelve un ``timedelta`` que desborde: axes lo resta de una fecha
    (``axes/attempts.py``), y un ``OverflowError`` ahí es un 500 en cada intento
    de login, para todo el mundo.
    """
    try:
        guardado = ConfiguracionSistema.get_config().horas_de_bloqueo
    except ErrorDeBaseDeDatos:
        logger.warning(
            "No se pudieron leer las horas de bloqueo de la configuración; "
            "se usa el respaldo de %s.", HORAS_DE_BLOQUEO_POR_DEFECTO,
        )
        guardado = HORAS_DE_BLOQUEO_POR_DEFECTO
    horas = _acotado(
        guardado, HORAS_DE_BLOQUEO_MINIMO, HORAS_DE_BLOQUEO_MAXIMO,
        "Las horas de bloqueo",
    )
    if not horas:
        return BLOQUEO_SIN_CADUCIDAD
    return timedelta(hours=horas)


def minutos_de_sesion():
    """Minutos de inactividad antes de cerrar la sesión."""
    try:
        guardado = ConfiguracionSistema.get_config().sesion_minutos
    except ErrorDeBaseDeDatos:
        respaldo = settings.SESSION_COOKIE_AGE // 60
        logger.warning(
            "No se pudieron leer los minutos de sesión de la configuración; "
            "se usa el respaldo de %s.", respaldo,
        )
        return respaldo
    return _acotado(
        guardado, SESION_MINUTOS_MINIMO, SESION_MINUTOS_MAXIMO,
        "Los minutos de sesión",
    )


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
            guardado = ConfiguracionSistema.get_config().longitud_minima_password
        except ErrorDeBaseDeDatos:
            logger.warning(
                "No se pudo leer la longitud mínima de contraseña de la "
                "configuración; se usa el respaldo de %s.", self.min_length,
            )
            return self.min_length
        return _acotado(
            guardado, LONGITUD_MINIMA_MINIMA, LONGITUD_MINIMA_MAXIMA,
            "La longitud mínima de la contraseña",
        )

    def validate(self, password, user=None):
        # Se delega en una instancia nueva en vez de reasignar self.min_length:
        # el validador es compartido entre peticiones y mutarlo no es seguro
        # con varios hilos. Así además el mensaje de error sigue siendo el de
        # Django, ya traducido.
        MinimumLengthValidator(self.longitud_minima()).validate(password, user)

    def get_help_text(self):
        return MinimumLengthValidator(self.longitud_minima()).get_help_text()
