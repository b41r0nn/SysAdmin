"""Texto de un fallo del servidor de correo, sin la credencial dentro.

Vive en su propio módulo porque lo necesitan **los dos** caminos que escriben
ese texto, y antes solo lo tenía el que casi no corre:

- ``administracion.views.correo`` lo pinta en pantalla (la prueba de envío);
- ``notificaciones.services`` lo **guarda en la base de datos**
  (``NotificacionEmail.error``), y ese es el camino del cron, el único que corre
  en producción.

El segundo manda sobre el diseño. Una fila de la cola con error no se purgaba
nunca (es ``enviado=False`` por definición), se pinta en la pantalla de Correo
—visible para cualquier rol con ``administracion:escritura``, que con la matriz
editable puede no ser quien configuró la credencial— y se ve desde ``/admin/``.
Un secreto ahí se queda para siempre y entra en cada respaldo.

Hace falta de verdad, no es paranoia: ``smtplib`` mete en la excepción la
respuesta del servidor **tal cual**, y la respuesta a un AUTH fallido puede
repetir lo que le mandamos.

Tres reglas y ninguna es de estilo:

1. **El reemplazo va ANTES del recorte.** Al revés, una contraseña partida por
   el límite dejaría la mitad a la vista.
2. **Esto no puede reventar nunca.** Se llama siempre desde dentro de un
   ``except``, y necesita la contraseña en claro para tacharla:
   ``get_smtp_password()`` lanza ``InvalidToken`` si la clave Fernet rotó sin
   ``rotar_clave_vault`` o si la base se restauró en otro host. Un ``except``
   que falla dentro de un ``except`` convierte un aviso de correo en un 500 y,
   en el cron, en una corrida muerta. Si algo falla se guarda
   ``TEXTO_GENERICO``: lo que no se puede tachar no se guarda.
3. **No se tacha de más.** Un error que no lleva la credencial se guarda
   legible y entero: si se tachara de más, el administrador perdería el
   diagnóstico y no lo notaría ninguna prueba.

**Deuda conocida.** El tachado caza el literal de la contraseña y las dos
formas en que ``smtplib`` la manda por el cable (ver ``_literales_a_tachar``),
pero no puede cubrir cualquier codificación que se invente un servidor al
devolver lo recibido. Cerrarlo del todo exigiría no guardar la respuesta del
servidor —solo un código y una clasificación—, y eso le quita al administrador
el único diagnóstico que tiene cuando un relé corporativo contesta algo raro.
Se deja así a propósito.
"""

import logging
from email.base64mime import body_encode

logger = logging.getLogger(__name__)

# Recorte del texto. La pantalla muestra menos que lo que se guarda: en la
# pantalla el texto va dentro de un mensaje de Bootstrap y 2000 caracteres de
# respuesta SMTP tapan la página.
LARGO_MAXIMO_PANTALLA = 500
LARGO_MAXIMO_GUARDADO = 2000

OCULTA = "(oculta)"
TEXTO_GENERICO = (
    "El servidor de correo falló y el detalle no se pudo guardar sin riesgo de "
    "incluir la contraseña configurada (¿cambió PASSWORDS_ENCRYPTION_KEY?). "
    "Revisa Configuración › Correo."
)


def _literales_a_tachar(secreto, usuario):
    """La contraseña y las formas en que ``smtplib`` la manda por el cable.

    El AUTH de SMTP viaja en base64 (``smtplib.SMTP.auth`` codifica la respuesta
    con ``email.base64mime.body_encode(..., eol="")``), así que un servidor que
    repita el argumento recibido devuelve el blob y no el literal:

    - **AUTH LOGIN** manda la contraseña sola, en base64;
    - **AUTH PLAIN** manda ``"\\0usuario\\0contraseña"``, en base64.

    CRAM-MD5 manda un HMAC, que no se puede reconstruir sin el desafío y
    tampoco revela la contraseña, así que no hay nada que tachar ahí.

    Se devuelven de más largo a más corto: el blob de PLAIN puede contener
    trozos del de LOGIN, y tachar primero el corto partiría el largo.
    """
    plano = secreto.encode()
    literales = {
        secreto,
        body_encode(plano, eol=""),
        body_encode(b"\0" + usuario.encode() + b"\0" + plano, eol=""),
    }
    return sorted(literales, key=len, reverse=True)


def texto_de_error_smtp(exc, config, largo=LARGO_MAXIMO_PANTALLA):
    """Texto del fallo ``exc`` sin la credencial de ``config``, recortado a ``largo``."""
    try:
        texto = str(exc)
        secreto = config.get_smtp_password()
        usuario = config.smtp_usuario or ""
        if secreto:
            for literal in _literales_a_tachar(secreto, usuario):
                texto = texto.replace(literal, OCULTA)
    except Exception as fallo:
        # Solo el NOMBRE de la excepción: el mensaje de una excepción cualquiera
        # podría ser el del servidor, que es justo lo que no se quiere repetir.
        logger.warning(
            "No se pudo tachar la credencial del error de correo (%s); se usa "
            "el texto genérico.", type(fallo).__name__,
        )
        return TEXTO_GENERICO
    return texto[:largo]
