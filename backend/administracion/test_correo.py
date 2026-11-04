"""Pruebas de la pantalla de Correo: SMTP, remitente, prueba de envío y cola.

Aquí vive la única credencial cifrada de la configuración, así que las pruebas
que importan no son las que comprueban que un campo se guarda, sino las cinco
que vigilan el secreto:

1. guardar con la casilla de la contraseña vacía conserva la guardada;
2. ningún ``RegistroAuditoria`` contiene la contraseña, ni la nueva ni la
   anterior (y la prueba lo comprueba con una aserción **positiva**, para que no
   pueda pasar en verde sin haber auditado nada);
3. el mensaje de error de la pantalla de prueba no la deja ver;
4. el correo de prueba no pasa por ``NotificacionEmail``, porque esa tabla es un
   histórico que otro proceso reenvía;
5. **la columna ``NotificacionEmail.error`` tampoco la contiene**, que es el
   camino del cron y el único que corre en producción. Esa fila no se purgaba
   nunca (``enviado=False``), se pinta en la pantalla de Correo y se ve desde
   ``/admin/``: un secreto ahí se queda para siempre y entra en cada respaldo.
"""

from smtplib import SMTPAuthenticationError
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from notificaciones.models import NotificacionEmail
from notificaciones.services import (
    MAX_INTENTOS_EMAIL,
    _get_smtp_connection,
    procesar_cola_email,
)

from .forms import ConfiguracionForm, CorreoForm
from .models import ConfiguracionSistema, RegistroAuditoria

SECRETO = "Sup3rS3cr3ta!"
CAMPOS_SMTP = (
    "smtp_host",
    "smtp_puerto",
    "smtp_usuario",
    "smtp_password",
    "smtp_usa_tls",
    "smtp_usa_ssl",
)


def _cuenta(rol, username):
    return get_user_model().objects.create_user(
        username=username, password="clavelargadeseguridad", rol=rol,
    )


def _datos_correo(config, **cambios):
    """POST completo de la pantalla de Correo, con la contraseña en blanco."""
    datos = {
        "smtp_host": config.smtp_host,
        "smtp_puerto": config.smtp_puerto,
        "smtp_usuario": config.smtp_usuario,
        "correo_remitente": config.correo_remitente,
        "smtp_password": "",
    }
    if config.smtp_usa_tls:
        datos["smtp_usa_tls"] = "on"
    if config.smtp_usa_ssl:
        datos["smtp_usa_ssl"] = "on"
    datos.update(cambios)
    return datos


class CorreoConfiguracionTests(TestCase):
    """La pantalla que guarda el servidor, el usuario, el remitente y la clave."""

    def setUp(self):
        self.config = ConfiguracionSistema.get_config()
        self.config.smtp_host = "smtp.office365.com"
        self.config.smtp_usuario = "soporte@redihos.co"
        self.config.save()
        self.superadmin = _cuenta("superadmin", "correo_sa")
        self.client.force_login(self.superadmin)

    def _post(self, **cambios):
        return self.client.post(
            reverse("administracion:correo"), _datos_correo(self.config, **cambios),
        )

    def test_la_pantalla_abre_y_renderiza_su_plantilla(self):
        resp = self.client.get(reverse("administracion:correo"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "administracion/correo_form.html")
        self.assertContains(resp, 'name="smtp_host"')
        self.assertContains(resp, 'name="smtp_password"')
        self.assertContains(resp, 'name="correo_remitente"')

    def test_la_contrasena_guardada_no_se_renderiza_nunca(self):
        self.config.set_smtp_password(SECRETO)
        self.config.save()
        resp = self.client.get(reverse("administracion:correo"))
        self.assertNotContains(resp, SECRETO)

    def test_guardar_sin_contrasena_conserva_la_guardada(self):
        """Foco de revisión 5: la casilla en blanco no borra la credencial."""
        self.config.set_smtp_password("original")
        self.config.save()

        resp = self._post(smtp_usuario="otro@redihos.co", smtp_password="")

        self.assertRedirects(resp, reverse("administracion:correo"))
        config = ConfiguracionSistema.get_config()
        self.assertEqual(config.get_smtp_password(), "original")
        self.assertEqual(config.smtp_usuario, "otro@redihos.co")

    def test_la_contrasena_nueva_reemplaza_la_anterior(self):
        self.config.set_smtp_password("original")
        self.config.save()

        self._post(smtp_password=SECRETO)

        self.assertEqual(ConfiguracionSistema.get_config().get_smtp_password(), SECRETO)

    def test_la_contrasena_nunca_aparece_en_la_auditoria(self):
        self._post(smtp_password=SECRETO)

        registros = list(RegistroAuditoria.objects.filter(accion="configurar"))
        self.assertEqual(len(registros), 1)
        self.assertIn("(cambiada)", registros[0].detalle)
        for registro in registros:
            for campo in registro._meta.get_fields():
                if not getattr(campo, "concrete", False) or campo.is_relation:
                    continue
                self.assertNotIn(SECRETO, str(getattr(registro, campo.name)), campo.name)

    def test_el_remitente_se_guarda_y_queda_auditado(self):
        self._post(correo_remitente="avisos@redihos.co")

        self.assertEqual(
            ConfiguracionSistema.get_config().correo_remitente, "avisos@redihos.co",
        )
        detalles = " ".join(RegistroAuditoria.objects.values_list("detalle", flat=True))
        self.assertIn("avisos@redihos.co", detalles)

    def test_el_remitente_vacio_cae_al_usuario_smtp(self):
        config = ConfiguracionSistema.get_config()
        self.assertEqual(config.correo_remitente, "")
        self.assertEqual(config.remitente_efectivo(), config.smtp_usuario)

    def test_el_remitente_puesto_gana_al_usuario_smtp(self):
        self.config.correo_remitente = "avisos@redihos.co"
        self.assertEqual(self.config.remitente_efectivo(), "avisos@redihos.co")

    def test_el_puerto_vacio_cae_a_587(self):
        self._post(smtp_puerto="")
        self.assertEqual(ConfiguracionSistema.get_config().smtp_puerto, 587)

    def test_un_tecnico_no_puede_abrir_la_pantalla(self):
        self.client.force_login(_cuenta("tecnico", "correo_tec_ver"))
        resp = self.client.get(reverse("administracion:correo"))
        self.assertRedirects(resp, reverse("core:dashboard"))


class EmpresaSinCamposSmtpTests(TestCase):
    """R13: los campos SMTP viven en una sola pantalla, la auditada.

    Dos formularios escribiendo la misma credencial —uno auditado y el otro no—
    es peor que no tener la pantalla nueva.
    """

    def setUp(self):
        self.config = ConfiguracionSistema.get_config()
        self.client.force_login(_cuenta("superadmin", "empresa_sa"))

    def test_el_formulario_de_empresa_no_declara_ningun_campo_smtp(self):
        campos = ConfiguracionForm().fields
        for campo in CAMPOS_SMTP + ("correo_remitente",):
            self.assertNotIn(campo, campos)

    def test_el_formulario_de_correo_los_declara_todos(self):
        campos = CorreoForm().fields
        for campo in CAMPOS_SMTP + ("correo_remitente",):
            self.assertIn(campo, campos)

    def test_la_pantalla_de_empresa_ya_no_pinta_el_bloque_de_smtp(self):
        resp = self.client.get(reverse("administracion:configuracion"))
        self.assertNotContains(resp, 'name="smtp_host"')
        self.assertNotContains(resp, 'name="smtp_password"')
        self.assertNotContains(resp, "Correo SMTP")

    def test_la_pantalla_de_empresa_no_puede_tocar_la_contrasena(self):
        """Sin el save() movido quedaría código muerto tocando la credencial."""
        self.config.set_smtp_password(SECRETO)
        self.config.save()

        self.client.post(
            reverse("administracion:configuracion"),
            {"nombre_empresa": "Clinica X", "smtp_password": "intruso"},
        )

        self.assertEqual(ConfiguracionSistema.get_config().get_smtp_password(), SECRETO)

    def test_el_cambio_de_empresa_queda_auditado(self):
        """Añadido del coordinador: la mitad que se queda también deja rastro."""
        self.client.post(
            reverse("administracion:configuracion"),
            {
                "nombre_empresa": "Clinica X",
                "pie_firma_reporte": self.config.pie_firma_reporte,
            },
        )

        detalle = RegistroAuditoria.objects.get(accion="configurar").detalle
        self.assertIn("Nombre de la empresa", detalle)
        self.assertIn("REDIHOS S.A.S", detalle)
        self.assertIn("Clinica X", detalle)


class AuditarSecretoDelCorreoTests(TestCase):
    """Las tres pruebas del secreto, mudadas del formulario de Empresa al nuevo.

    Trabajan sobre el formulario y no sobre la vista a propósito: lo que vigilan
    es ``auditar_cambios`` con ``secretos=("smtp_password",)``.
    """

    def setUp(self):
        self.user = _cuenta("superadmin", "aud_correo")
        self.config = ConfiguracionSistema.get_config()
        self.config.smtp_host = "smtp.office365.com"
        self.config.smtp_usuario = "soporte@redihos.co"
        self.config.save()

    def _form(self, **cambios):
        from .auditoria import auditar_cambios

        form = CorreoForm(_datos_correo(self.config, **cambios), instance=self.config)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.auditar = auditar_cambios
        return form

    def test_un_campo_declarado_secreto_se_registra_sin_su_valor(self):
        form = self._form(smtp_password=SECRETO)
        self.assertEqual(self.auditar(self.user, form, secretos=("smtp_password",)), 1)
        detalles = " ".join(RegistroAuditoria.objects.values_list("detalle", flat=True))
        self.assertNotIn(SECRETO, detalles)
        self.assertIn("(cambiada)", detalles)
        self.assertIn("Contraseña SMTP", detalles)

    def test_ningun_registro_de_auditoria_contiene_el_secreto_en_claro(self):
        form = self._form(smtp_password=SECRETO, smtp_usuario="nuevo@redihos.co")
        self.auditar(self.user, form, secretos=("smtp_password",), ip="10.0.0.1")
        self.assertEqual(RegistroAuditoria.objects.count(), 2)
        for registro in RegistroAuditoria.objects.all():
            for campo in registro._meta.get_fields():
                if not getattr(campo, "concrete", False) or campo.is_relation:
                    continue
                self.assertNotIn(SECRETO, str(getattr(registro, campo.name)), campo.name)

    def test_el_secreto_anterior_tampoco_entra_en_el_texto(self):
        """Las dos aserciones negativas no bastan: sin la positiva, un formulario
        que no audite nada dejaría ``detalles`` vacío y la prueba pasaría en
        falso verde. Y es justo la prueba del foco de revisión 5."""
        self.config.set_smtp_password(SECRETO)
        self.config.save()

        form = self._form(smtp_password="Otra#Clave9")
        self.auditar(self.user, form, secretos=("smtp_password",))

        detalles = " ".join(RegistroAuditoria.objects.values_list("detalle", flat=True))
        self.assertEqual(RegistroAuditoria.objects.count(), 1)
        self.assertIn("(cambiada)", detalles)
        self.assertNotIn(SECRETO, detalles)
        self.assertNotIn("Otra#Clave9", detalles)


class ProbarCorreoTests(TestCase):
    """El botón «Enviar correo de prueba»: el único camino SMTP que sale de una
    petición web, y el que hace evidente la falta del ``timeout``."""

    def setUp(self):
        self.config = ConfiguracionSistema.get_config()
        self.config.smtp_host = "smtp.office365.com"
        self.config.smtp_usuario = "soporte@redihos.co"
        self.config.set_smtp_password(SECRETO)
        self.config.save()
        self.client.force_login(_cuenta("superadmin", "probar_sa"))

    def _probar(self, destino="a@b.co", **extra):
        return self.client.post(
            reverse("administracion:probar_correo"), {"destino": destino, **extra},
            follow=True,
        )

    def test_probar_envio_manda_un_correo_y_lo_reporta(self):
        with patch("administracion.views.correo._get_smtp_connection") as conexion:
            resp = self._probar()
        self.assertContains(resp, "Correo de prueba enviado")
        self.assertEqual(conexion.return_value.send_messages.call_count, 1)

    def test_el_correo_de_prueba_usa_el_remitente_efectivo(self):
        self.config.correo_remitente = "avisos@redihos.co"
        self.config.save()
        with patch("administracion.views.correo._get_smtp_connection") as conexion:
            self._probar()
        mensaje = conexion.return_value.send_messages.call_args[0][0][0]
        self.assertEqual(mensaje.from_email, "avisos@redihos.co")
        self.assertEqual(mensaje.to, ["a@b.co"])

    def test_el_correo_de_prueba_no_pasa_por_la_cola(self):
        """La cola es un histórico que el cron reenvía: una prueba no entra ahí."""
        with patch("administracion.views.correo._get_smtp_connection"):
            self._probar()
        self.assertEqual(NotificacionEmail.objects.count(), 0)

    def test_la_prueba_queda_auditada_con_el_destino_y_sin_la_credencial(self):
        with patch("administracion.views.correo._get_smtp_connection"):
            self._probar()
        detalle = RegistroAuditoria.objects.get(accion="configurar").detalle
        self.assertIn("a@b.co", detalle)
        self.assertNotIn(SECRETO, detalle)

    def test_probar_envio_muestra_el_error_textual_del_servidor(self):
        with patch("administracion.views.correo._get_smtp_connection") as conexion:
            conexion.return_value.send_messages.side_effect = SMTPAuthenticationError(
                535, b"5.7.3 Authentication unsuccessful",
            )
            resp = self._probar()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Authentication unsuccessful")

    def test_la_contrasena_no_aparece_en_el_mensaje_de_error(self):
        """Un ``except`` que vuelque la conexión o la respuesta del servidor tal
        cual filtra el secreto a la pantalla."""
        with patch("administracion.views.correo._get_smtp_connection") as conexion:
            conexion.return_value.send_messages.side_effect = SMTPAuthenticationError(
                535, f"5.7.8 rechazado: user=soporte pass={SECRETO}".encode(),
            )
            resp = self._probar()
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, SECRETO)
        self.assertContains(resp, "(oculta)")
        detalles = " ".join(RegistroAuditoria.objects.values_list("detalle", flat=True))
        self.assertNotIn(SECRETO, detalles)

    def test_probar_envio_sin_smtp_configurado_avisa_y_no_revienta(self):
        self.config.smtp_host = ""
        self.config.save()

        resp = self._probar()

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No hay servidor SMTP configurado")
        self.assertEqual(NotificacionEmail.objects.count(), 0)

    def test_probar_envio_sin_destino_avisa(self):
        with patch("administracion.views.correo._get_smtp_connection") as conexion:
            resp = self._probar(destino="   ")
        self.assertContains(resp, "Escribe la dirección")
        conexion.assert_not_called()

    def test_probar_envio_no_acepta_get(self):
        resp = self.client.get(reverse("administracion:probar_correo"))
        self.assertEqual(resp.status_code, 405)

    def test_un_tecnico_no_puede_probar_el_correo(self):
        self.client.force_login(_cuenta("tecnico", "probar_tec"))
        with patch("administracion.views.correo._get_smtp_connection") as conexion:
            resp = self.client.post(
                reverse("administracion:probar_correo"), {"destino": "a@b.co"},
            )
        self.assertRedirects(resp, reverse("core:dashboard"))
        conexion.assert_not_called()


class ColaDeCorreoTests(TestCase):
    """Los conteos de la cola y el botón de reintentar los fallidos."""

    def setUp(self):
        self.client.force_login(_cuenta("superadmin", "cola_sa"))

    def _encolar(self, asunto, **campos):
        return NotificacionEmail.objects.create(
            destinatario="a@b.co", asunto=asunto, cuerpo="C", **campos,
        )

    def test_la_pantalla_muestra_pendientes_y_fallidos(self):
        self._encolar("pendiente")
        self._encolar("fallida", intentos=MAX_INTENTOS_EMAIL, error="smtp 535")
        self._encolar("enviada", enviado=True)

        resp = self.client.get(reverse("administracion:correo"))

        self.assertEqual(resp.context["pendientes"], 1)
        self.assertEqual(resp.context["fallidos"], 1)
        self.assertContains(resp, "Cola de correo")

    def test_reintentar_pone_los_fallidos_de_vuelta_en_la_cola(self):
        fallida = self._encolar("fallida", intentos=MAX_INTENTOS_EMAIL, error="smtp 535")
        enviada = self._encolar("enviada", enviado=True, intentos=1)

        resp = self.client.post(reverse("administracion:reintentar_correos"))

        self.assertRedirects(resp, reverse("administracion:correo"))
        fallida.refresh_from_db()
        self.assertEqual(fallida.intentos, 0)
        self.assertEqual(fallida.error, "")
        enviada.refresh_from_db()
        self.assertEqual(enviada.intentos, 1)

    def test_reintentar_queda_auditado(self):
        self._encolar("fallida", intentos=MAX_INTENTOS_EMAIL, error="smtp 535")
        self.client.post(reverse("administracion:reintentar_correos"))
        self.assertTrue(
            RegistroAuditoria.objects.filter(accion="configurar").exists()
        )

    def test_reintentar_no_acepta_get(self):
        resp = self.client.get(reverse("administracion:reintentar_correos"))
        self.assertEqual(resp.status_code, 405)

    def test_un_tecnico_no_puede_reintentar(self):
        fallida = self._encolar("fallida", intentos=MAX_INTENTOS_EMAIL, error="smtp 535")
        self.client.force_login(_cuenta("tecnico", "cola_tec"))
        resp = self.client.post(reverse("administracion:reintentar_correos"))
        self.assertRedirects(resp, reverse("core:dashboard"))
        fallida.refresh_from_db()
        self.assertEqual(fallida.intentos, MAX_INTENTOS_EMAIL)


class _ConexionQueFallaAlAbrir:
    """Conexión falsa cuyo ``open()`` lanza lo que diga el servidor.

    Es el camino del AUTH: ``connection.open()`` autentica, y la respuesta a un
    AUTH fallido puede repetir lo que le mandamos.
    """

    def __init__(self, respuesta):
        self.respuesta = respuesta

    def open(self):
        raise SMTPAuthenticationError(535, self.respuesta.encode())

    def close(self):
        pass


class _ConexionQueFallaAlEnviar:
    def __init__(self, respuesta):
        self.respuesta = respuesta

    def open(self):
        return True

    def send_messages(self, mensajes):
        raise SMTPAuthenticationError(535, self.respuesta.encode())

    def close(self):
        pass


class CredencialFueraDeLaColaTests(TestCase):
    """La contraseña del SMTP no puede quedar guardada en la base.

    La pantalla de prueba de envío ya tachaba la credencial, pero el camino que
    corre de verdad —``procesar_cola_email()``, el del cron— escribía
    ``str(exc)`` tal cual en ``NotificacionEmail.error``, en una fila que la
    limpieza no purgaba, que se pinta en pantalla y que es visible desde
    ``/admin/``.
    """

    def setUp(self):
        self.config = ConfiguracionSistema.get_config()
        self.config.smtp_host = "smtp.office365.com"
        self.config.smtp_usuario = "soporte@redihos.co"
        self.config.set_smtp_password(SECRETO)
        self.config.save()

    def _encolar(self):
        return NotificacionEmail.objects.create(
            destinatario="a@b.co", asunto="S", cuerpo="C",
        )

    def _procesar_con(self, conexion):
        with patch("notificaciones.services.get_connection", return_value=conexion):
            return procesar_cola_email()

    def test_un_fallo_al_abrir_la_conexion_no_guarda_la_credencial(self):
        """El crítico: es el camino del AUTH y el que corre en producción."""
        self._encolar()

        total, enviados, fallos, quedan = self._procesar_con(
            _ConexionQueFallaAlAbrir(f"5.7.8 rechazado: user=soporte pass={SECRETO}")
        )

        correo = NotificacionEmail.objects.get()
        self.assertEqual((total, enviados, fallos), (1, 0, 1))
        self.assertNotIn(SECRETO, correo.error)
        self.assertIn("(oculta)", correo.error)
        self.assertEqual(correo.intentos, 1)

    def test_un_fallo_al_enviar_un_mensaje_no_guarda_la_credencial(self):
        """La segunda escritura cruda: el fallo por mensaje, no por conexión."""
        self._encolar()

        self._procesar_con(
            _ConexionQueFallaAlEnviar(f"5.7.8 rechazado: pass={SECRETO}")
        )

        correo = NotificacionEmail.objects.get()
        self.assertNotIn(SECRETO, correo.error)
        self.assertIn("(oculta)", correo.error)

    def test_la_credencial_en_base64_tampoco_se_guarda(self):
        """El AUTH de SMTP viaja en base64: el literal exacto no basta.

        ``smtplib`` manda ``base64(contraseña)`` con AUTH LOGIN y
        ``base64("\\0usuario\\0contraseña")`` con AUTH PLAIN. Un servidor que
        repita el argumento recibido devuelve el blob, no el literal.
        """
        from email.base64mime import body_encode

        blob = body_encode(f"\0soporte@redihos.co\0{SECRETO}".encode(), eol="")
        solo_clave = body_encode(SECRETO.encode(), eol="")
        self._encolar()

        self._procesar_con(
            _ConexionQueFallaAlAbrir(f"5.7.8 rechazado: {blob} / {solo_clave}")
        )

        correo = NotificacionEmail.objects.get()
        self.assertNotIn(blob, correo.error)
        self.assertNotIn(solo_clave, correo.error)

    def test_si_el_descifrado_falla_no_revienta_ni_guarda_nada_crudo(self):
        """El tachado necesita la clave en claro, y descifrarla puede fallar.

        ``get_smtp_password()`` lanza ``InvalidToken`` si la clave Fernet rotó
        sin ``rotar_clave_vault`` o si la base se restauró en otro host. Un
        ``except`` que falla dentro de un ``except`` convierte un aviso de correo
        en un cron muerto, y aquí además revienta antes: hoy
        ``_get_smtp_connection()`` se construye FUERA del ``try``.
        """
        from cryptography.fernet import InvalidToken

        from administracion.errores_correo import TEXTO_GENERICO

        self._encolar()
        fallo = patch.object(
            ConfiguracionSistema, "get_smtp_password", side_effect=InvalidToken(),
        )
        with fallo, patch("notificaciones.services.get_connection"):
            total, enviados, fallos, quedan = procesar_cola_email()

        correo = NotificacionEmail.objects.get()
        self.assertEqual((total, enviados, fallos), (1, 0, 1))
        self.assertEqual(correo.error, TEXTO_GENERICO)
        self.assertEqual(correo.intentos, 1)

    def test_tls_y_ssl_a_la_vez_no_matan_el_cron(self):
        """``get_connection()`` lanza ``ValueError`` con las dos marcadas.

        Pasaba fuera del ``try``, así que el cron reventaba contra su propio
        docstring, que promete que nunca revienta, y la portada seguía contando
        ``error=""``: un fallo de correo en cada corrida sin marcar nada.
        """
        ConfiguracionSistema.objects.filter(pk=1).update(
            smtp_usa_tls=True, smtp_usa_ssl=True,
        )
        self._encolar()

        total, enviados, fallos, quedan = procesar_cola_email()

        correo = NotificacionEmail.objects.get()
        self.assertEqual((total, enviados, fallos), (1, 0, 1))
        self.assertTrue(correo.error)
        self.assertNotIn(SECRETO, correo.error)

    def test_un_error_que_no_lleva_la_credencial_se_guarda_legible(self):
        """Contraprueba, y no es decorativa: si se tacha de más, el
        administrador pierde el diagnóstico y no lo nota ninguna prueba."""
        self._encolar()

        self._procesar_con(
            _ConexionQueFallaAlAbrir("5.7.1 Relay access denied para a@b.co")
        )

        correo = NotificacionEmail.objects.get()
        self.assertIn("Relay access denied", correo.error)
        self.assertIn("a@b.co", correo.error)
        self.assertNotIn("(oculta)", correo.error)

    def test_una_cola_sin_credencial_configurada_sigue_guardando_el_error(self):
        """Sin contraseña guardada no hay nada que tachar y el texto va entero."""
        ConfiguracionSistema.objects.filter(pk=1).update(smtp_password_cifrado="")
        self._encolar()

        self._procesar_con(_ConexionQueFallaAlAbrir("5.7.1 Relay access denied"))

        self.assertIn("Relay access denied", NotificacionEmail.objects.get().error)

    def test_el_error_no_se_puede_editar_desde_el_admin(self):
        """La segunda puerta: ``/admin/`` no declaraba ni ``fields`` ni ``exclude``."""
        from notificaciones.admin import NotificacionEmailAdmin

        self.assertIn("error", NotificacionEmailAdmin.readonly_fields)


class TlsYSslExcluyentesTests(TestCase):
    """Las dos casillas juntas son alcanzables desde la pantalla."""

    def setUp(self):
        self.config = ConfiguracionSistema.get_config()
        self.config.smtp_host = "smtp.office365.com"
        self.config.smtp_usuario = "soporte@redihos.co"
        self.config.save()

    def test_el_formulario_rechaza_tls_y_ssl_a_la_vez(self):
        form = CorreoForm(
            _datos_correo(self.config, smtp_usa_tls="on", smtp_usa_ssl="on"),
            instance=self.config,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("STARTTLS", " ".join(form.errors["__all__"]))

    def test_el_formulario_acepta_solo_una_de_las_dos(self):
        """Contraprueba: la configuración normal (STARTTLS en el 587) pasa."""
        for marcada in ("smtp_usa_tls", "smtp_usa_ssl"):
            with self.subTest(marcada=marcada):
                datos = _datos_correo(self.config)
                datos.pop("smtp_usa_tls", None)
                datos.pop("smtp_usa_ssl", None)
                datos[marcada] = "on"
                form = CorreoForm(datos, instance=self.config)
                self.assertTrue(form.is_valid(), form.errors)

    def test_el_formulario_acepta_las_dos_sin_marcar(self):
        datos = _datos_correo(self.config)
        datos.pop("smtp_usa_tls", None)
        datos.pop("smtp_usa_ssl", None)
        form = CorreoForm(datos, instance=self.config)
        self.assertTrue(form.is_valid(), form.errors)


class ConexionSmtpTests(TestCase):
    """El ``timeout`` y el remitente en el camino real del correo."""

    def setUp(self):
        self.config = ConfiguracionSistema.get_config()
        self.config.smtp_host = "smtp.office365.com"
        self.config.smtp_usuario = "soporte@redihos.co"
        self.config.save()

    @patch("notificaciones.services.get_connection")
    def test_la_conexion_smtp_lleva_timeout(self, conexion):
        """Sin timeout, un host inalcanzable cuelga el worker de gunicorn hasta
        el GUNICORN_TIMEOUT: la pantalla de prueba llama a esto desde una
        petición web, no solo el cron."""
        _get_smtp_connection()
        self.assertEqual(conexion.call_args.kwargs["timeout"], 10)

    @patch("notificaciones.services.get_connection")
    def test_la_cola_envia_con_el_remitente_efectivo(self, conexion):
        """Sin esto el remitente sería decorativo: el From de la cola se queda en
        el DEFAULT_FROM_EMAIL de Django (``webmaster@localhost``), que ningún
        relé corporativo acepta."""
        self.config.correo_remitente = "avisos@redihos.co"
        self.config.save()
        NotificacionEmail.objects.create(destinatario="a@b.co", asunto="S", cuerpo="C")

        procesar_cola_email()

        mensaje = conexion.return_value.send_messages.call_args[0][0][0]
        self.assertEqual(mensaje.from_email, "avisos@redihos.co")
