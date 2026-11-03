"""Pruebas de la política de seguridad configurable.

Cuatro valores que estaban fijos en los settings pasan a la base de datos: los
minutos de sesión, los intentos antes de bloquear, las horas de bloqueo y la
longitud mínima de la contraseña. Todo lo de aquí cuelga del camino del login,
así que las pruebas que importan no son las que comprueban que una función
devuelve el número correcto, sino las que comprueban que **axes y Django de
verdad la llaman**.
"""

from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse

from administracion.forms_seguridad import SeguridadForm
from administracion.models import ConfiguracionSistema, RegistroAuditoria
from administracion.seguridad import (
    HORAS_DE_BLOQUEO_POR_DEFECTO,
    INTENTOS_POR_DEFECTO,
    LongitudMinimaConfigurable,
    limite_de_intentos,
    minutos_de_sesion,
    tiempo_de_bloqueo,
)

CLAVE_BUENA = "clavelargadeseguridad"


def _config(**cambios):
    """Escribe en la fila 1 con update(): no dispara señales, como en producción."""
    ConfiguracionSistema.get_config()
    if cambios:
        ConfiguracionSistema.objects.filter(pk=1).update(**cambios)


class SeguridadConfigurableTests(TestCase):
    """Las tres lecturas y el validador, mirando la fila de configuración."""

    def setUp(self):
        _config()

    def test_el_limite_de_intentos_sale_de_la_configuracion(self):
        _config(intentos_antes_de_bloquear=3)
        self.assertEqual(limite_de_intentos(None, {}), 3)

    def test_el_tiempo_de_bloqueo_sale_de_la_configuracion(self):
        _config(horas_de_bloqueo=2)
        self.assertEqual(tiempo_de_bloqueo(None), timedelta(hours=2))

    def test_cero_horas_de_bloqueo_no_caduca(self):
        """Con 0 horas el bloqueo no se levanta solo: queda hasta que lo quiten.

        No se devuelve None aunque sea lo que axes documenta como «sin bloqueo
        temporal»: con AXES_COOLOFF_TIME puesto a una ruta con puntos, las
        guardas `if settings.AXES_COOLOFF_TIME is None` de axes no se activan y
        un None aquí revienta el login. Ver el docstring de tiempo_de_bloqueo.
        """
        _config(horas_de_bloqueo=0)
        bloqueo = tiempo_de_bloqueo(None)
        self.assertIsNotNone(bloqueo)
        self.assertGreater(bloqueo, timedelta(days=365 * 10))

    def test_la_longitud_minima_sale_de_la_configuracion(self):
        _config(longitud_minima_password=14)
        with self.assertRaises(ValidationError):
            LongitudMinimaConfigurable().validate("Trece1234567")  # 12 caracteres
        LongitudMinimaConfigurable().validate("Catorce1234567")  # 14 caracteres

    def test_el_validador_resuelve_la_longitud_en_cada_llamada(self):
        """Django instancia el validador una vez: no puede cachear el valor."""
        validador = LongitudMinimaConfigurable()
        _config(longitud_minima_password=8)
        validador.validate("ochochar")
        _config(longitud_minima_password=20)
        with self.assertRaises(ValidationError):
            validador.validate("ochochar")
        self.assertIn("20", validador.get_help_text())

    def test_el_validador_esta_conectado_en_los_settings(self):
        """Una función correcta que nadie llama es un fallo silencioso."""
        nombres = [v["NAME"] for v in settings.AUTH_PASSWORD_VALIDATORS]
        self.assertIn("administracion.seguridad.LongitudMinimaConfigurable", nombres)
        self.assertNotIn(
            "django.contrib.auth.password_validation.MinimumLengthValidator", nombres
        )
        _config(longitud_minima_password=14)
        with self.assertRaises(ValidationError):
            validate_password("Trece1234567")  # 12 < 14
        validate_password("Catorce1234567")

    def test_axes_resuelve_las_rutas_con_puntos_de_los_settings(self):
        """Rutas con puntos, no el callable importado (carga de apps)."""
        from axes.helpers import get_cool_off, get_failure_limit

        self.assertEqual(
            settings.AXES_FAILURE_LIMIT, "administracion.seguridad.limite_de_intentos"
        )
        self.assertEqual(
            settings.AXES_COOLOFF_TIME, "administracion.seguridad.tiempo_de_bloqueo"
        )
        _config(intentos_antes_de_bloquear=7, horas_de_bloqueo=3)
        self.assertEqual(get_failure_limit(None, {}), 7)
        self.assertEqual(get_cool_off(None), timedelta(hours=3))

    def test_los_valores_por_defecto_no_cambian_la_politica_de_hoy(self):
        config = ConfiguracionSistema.get_config()
        self.assertEqual(config.sesion_minutos, 30)
        self.assertEqual(config.intentos_antes_de_bloquear, 5)
        self.assertEqual(config.horas_de_bloqueo, 1)
        self.assertEqual(config.longitud_minima_password, 10)
        self.assertEqual(config.sesion_minutos * 60, settings.SESSION_COOKIE_AGE)

    def test_los_respaldos_coinciden_con_los_defaults_del_modelo(self):
        """Si uno de los dos se mueve, el respaldo cambiaría la política."""
        meta = ConfiguracionSistema._meta
        self.assertEqual(
            INTENTOS_POR_DEFECTO, meta.get_field("intentos_antes_de_bloquear").default
        )
        self.assertEqual(
            HORAS_DE_BLOQUEO_POR_DEFECTO, meta.get_field("horas_de_bloqueo").default
        )

    def test_el_help_text_de_horas_de_bloqueo_nombra_la_via_de_recuperacion(self):
        """Decir «0 = sin bloqueo» dejaría al administrador fuera sin salida."""
        texto = ConfiguracionSistema._meta.get_field("horas_de_bloqueo").help_text
        self.assertIn("axes_reset", texto)
        self.assertNotIn("sin bloqueo", texto.lower())

    def test_sin_configuracion_se_usan_los_valores_de_los_settings(self):
        """Cache frío o tabla vacía no pueden dejar la aplicación sin política.

        get_config() es un get_or_create: borrar la fila no prueba nada porque
        la vuelve a crear. Lo que tumba el login es que la LECTURA falle (base
        nueva, migrate a medias), así que se fuerza el DatabaseError.
        """
        fallo = mock.patch.object(
            ConfiguracionSistema, "get_config", side_effect=DatabaseError("no existe la tabla")
        )
        with fallo, self.assertLogs("administracion.seguridad", level="WARNING"):
            self.assertEqual(limite_de_intentos(None, {}), INTENTOS_POR_DEFECTO)
            self.assertEqual(
                tiempo_de_bloqueo(None), timedelta(hours=HORAS_DE_BLOQUEO_POR_DEFECTO)
            )
            self.assertEqual(minutos_de_sesion(), settings.SESSION_COOKIE_AGE // 60)
            with self.assertRaises(ValidationError):
                validate_password("corta123")  # 8 < 10, el respaldo del validador
            validate_password("DiezCarac1")  # 10 caracteres


class AxesBloqueoConfigurableTests(TestCase):
    """La prueba que importa: que axes de verdad llame al callable."""

    LOGIN = "/accounts/login/"

    def setUp(self):
        from axes.models import AccessAttempt, AccessFailureLog

        AccessAttempt.objects.all().delete()
        AccessFailureLog.objects.all().delete()
        _config()
        self.usuario = get_user_model().objects.create_user(
            username="seg_config", password=CLAVE_BUENA, rol="tecnico"
        )

    def _intento_fallido(self):
        return self.client.post(
            self.LOGIN, {"username": "seg_config", "password": "password-incorrecta"}
        )

    def test_axes_bloquea_al_numero_configurado(self):
        _config(intentos_antes_de_bloquear=2)
        self.assertEqual(self._intento_fallido().status_code, 200)
        # El intento que alcanza el límite ya responde con el bloqueo: axes marca
        # request.axes_locked_out en ese mismo request y su middleware lo traduce.
        self.assertEqual(self._intento_fallido().status_code, 429)
        self.assertEqual(self._intento_fallido().status_code, 429)
        # Y el bloqueo es real, no solo un código: ni con la clave correcta entra.
        resp = self.client.post(
            self.LOGIN, {"username": "seg_config", "password": CLAVE_BUENA}
        )
        self.assertEqual(resp.status_code, 429)

    def test_con_el_limite_de_por_defecto_el_segundo_intento_no_bloquea(self):
        """Contraprueba: si axes ignorara la configuración, 2 nunca bloquearía."""
        self.assertEqual(ConfiguracionSistema.get_config().intentos_antes_de_bloquear, 5)
        self.assertEqual(self._intento_fallido().status_code, 200)
        self.assertEqual(self._intento_fallido().status_code, 200)
        self.assertEqual(self._intento_fallido().status_code, 200)

    def test_con_cero_horas_de_bloqueo_el_login_sigue_respondiendo(self):
        """Regresión: un None en tiempo_de_bloqueo revienta el login con TypeError.

        Con AXES_COOLOFF_TIME como ruta con puntos, la guarda
        `if settings.AXES_COOLOFF_TIME is None` de axes/handlers/database.py:383
        nunca se cumple, así que get_cool_off_threshold() recibe None y lanza
        TypeError: un 500 en CADA intento de login, para todo el mundo.
        """
        _config(horas_de_bloqueo=0, intentos_antes_de_bloquear=2)
        self.assertEqual(self._intento_fallido().status_code, 200)
        self.assertEqual(self._intento_fallido().status_code, 429)

    def test_el_bloqueo_sigue_siendo_por_usuario_e_ip(self):
        """El cambio de settings no puede ampliar el alcance del bloqueo."""
        _config(intentos_antes_de_bloquear=2)
        for _ in range(2):
            self.client.post(
                self.LOGIN,
                {"username": "seg_config", "password": "mala"},
                HTTP_X_FORWARDED_FOR="10.0.0.5",
            )
        resp = self.client.post(
            self.LOGIN,
            {"username": "seg_config", "password": CLAVE_BUENA},
            HTTP_X_FORWARDED_FOR="10.0.0.6",
        )
        self.assertRedirects(resp, reverse("core:dashboard"))


class SesionConfigurableMiddlewareTests(TestCase):
    def setUp(self):
        _config()
        self.usuario = get_user_model().objects.create_user(
            username="seg_sesion", password=CLAVE_BUENA, rol="superadmin"
        )

    def test_el_middleware_fija_el_vencimiento_de_la_sesion(self):
        self.client.force_login(self.usuario)
        _config(sesion_minutos=5)
        self.client.get(reverse("core:dashboard"))
        self.assertEqual(self.client.session.get_expiry_age(), 300)

    def test_el_minutero_se_renueva_en_cada_peticion(self):
        """Es inactividad real, no tiempo desde el login."""
        self.client.force_login(self.usuario)
        _config(sesion_minutos=7)
        self.client.get(reverse("core:dashboard"))
        self.assertEqual(self.client.session.get_expiry_age(), 420)
        self.client.get(reverse("core:dashboard"))
        self.assertEqual(self.client.session.get_expiry_age(), 420)

    def test_un_anonimo_no_estrena_vencimiento(self):
        resp = self.client.get("/accounts/login/")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self.client.session.get("_session_expiry"))

    def test_si_la_lectura_falla_la_sesion_usa_el_valor_de_los_settings(self):
        self.client.force_login(self.usuario)
        _config(sesion_minutos=5)
        fallo = mock.patch.object(
            ConfiguracionSistema, "get_config", side_effect=DatabaseError("sin tabla")
        )
        with fallo, self.assertLogs("administracion.seguridad", level="WARNING"):
            self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)
        self.assertEqual(
            self.client.session.get_expiry_age(), settings.SESSION_COOKIE_AGE
        )

    def test_esta_registrado_despues_de_la_autenticacion(self):
        """Sin request.user no hay nada que decidir: el orden no es decorativo."""
        auth = "django.contrib.auth.middleware.AuthenticationMiddleware"
        propio = "administracion.middleware.SesionConfigurableMiddleware"
        self.assertIn(propio, settings.MIDDLEWARE)
        self.assertGreater(
            settings.MIDDLEWARE.index(propio), settings.MIDDLEWARE.index(auth)
        )


class SeguridadFormTests(TestCase):
    def setUp(self):
        _config()
        self.base = {
            "sesion_minutos": 30,
            "intentos_antes_de_bloquear": 5,
            "horas_de_bloqueo": 1,
            "longitud_minima_password": 10,
        }

    def _form(self, **cambios):
        datos = dict(self.base, **cambios)
        return SeguridadForm(datos, instance=ConfiguracionSistema.objects.get(pk=1))

    def test_el_formulario_rechaza_valores_que_dejan_fuera_al_usuario(self):
        """Foco de revisión 1: un 0 en sesion_minutos cierra la sesión en el
        mismo request en que se guarda."""
        for campo, valor in (
            ("sesion_minutos", 0),
            ("intentos_antes_de_bloquear", 0),
            ("longitud_minima_password", 4),
        ):
            with self.subTest(campo=campo):
                antes = getattr(ConfiguracionSistema.objects.get(pk=1), campo)
                form = self._form(**{campo: valor})
                self.assertFalse(form.is_valid())
                self.assertIn(campo, form.errors)
                self.assertEqual(
                    getattr(ConfiguracionSistema.objects.get(pk=1), campo), antes
                )

    def test_el_formulario_acepta_cero_horas_de_bloqueo(self):
        """0 horas es una política válida (bloqueo que no caduca), no un error."""
        form = self._form(horas_de_bloqueo=0)
        self.assertTrue(form.is_valid(), form.errors)

    def test_el_formulario_solo_toca_los_cuatro_campos_de_seguridad(self):
        self.assertEqual(
            list(SeguridadForm().fields),
            [
                "sesion_minutos",
                "intentos_antes_de_bloquear",
                "horas_de_bloqueo",
                "longitud_minima_password",
            ],
        )

    def test_la_pantalla_de_empresa_no_hereda_los_campos_nuevos(self):
        from administracion.forms import ConfiguracionForm

        for campo in self.base:
            self.assertNotIn(campo, ConfiguracionForm().fields)


class SeguridadVistaTests(TestCase):
    URL = "administracion:seguridad"

    def setUp(self):
        _config()
        self.superadmin = get_user_model().objects.create_user(
            username="seg_vista", password=CLAVE_BUENA, rol="superadmin"
        )
        self.client.force_login(self.superadmin)

    def test_la_pantalla_abre_y_renderiza_su_plantilla(self):
        resp = self.client.get(reverse(self.URL))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "administracion/seguridad_form.html")
        self.assertContains(resp, "Seguridad")
        # El aviso de las 0 horas tiene que estar a la vista, no solo en el modelo.
        self.assertContains(resp, "axes_reset")

    def test_el_cambio_queda_auditado(self):
        resp = self.client.post(
            reverse(self.URL),
            {
                "sesion_minutos": 45,
                "intentos_antes_de_bloquear": 3,
                "horas_de_bloqueo": 2,
                "longitud_minima_password": 12,
            },
        )
        self.assertRedirects(resp, reverse(self.URL))
        config = ConfiguracionSistema.objects.get(pk=1)
        self.assertEqual(config.sesion_minutos, 45)
        self.assertEqual(config.intentos_antes_de_bloquear, 3)
        self.assertEqual(config.horas_de_bloqueo, 2)
        self.assertEqual(config.longitud_minima_password, 12)

        registros = RegistroAuditoria.objects.filter(accion="configurar")
        self.assertEqual(registros.count(), 4)
        detalles = " ".join(registros.values_list("detalle", flat=True))
        self.assertIn("30 → 45", detalles)
        self.assertIn("Intentos antes de bloquear", detalles)
        self.assertNotIn("intentos_antes_de_bloquear", detalles)
        self.assertEqual(registros.first().modulo, "administracion")

    def test_un_post_invalido_no_guarda_ni_audita(self):
        resp = self.client.post(reverse(self.URL), dict(
            sesion_minutos=0, intentos_antes_de_bloquear=5,
            horas_de_bloqueo=1, longitud_minima_password=10,
        ))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ConfiguracionSistema.objects.get(pk=1).sesion_minutos, 30)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="configurar").exists())

    def test_un_rol_sin_escritura_no_entra(self):
        self.client.force_login(
            get_user_model().objects.create_user(
                username="seg_lectura", password=CLAVE_BUENA, rol="lectura"
            )
        )
        resp = self.client.get(reverse(self.URL))
        self.assertRedirects(resp, reverse("core:dashboard"))
