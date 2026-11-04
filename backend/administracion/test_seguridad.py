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
    HORAS_DE_BLOQUEO_MAXIMO,
    HORAS_DE_BLOQUEO_POR_DEFECTO,
    INTENTOS_MAXIMO,
    INTENTOS_POR_DEFECTO,
    LONGITUD_MINIMA_MAXIMA,
    SESION_MINUTOS_MAXIMO,
    LongitudMinimaConfigurable,
    limite_de_intentos,
    minutos_de_sesion,
    tiempo_de_bloqueo,
)

CLAVE_BUENA = "clavelargadeseguridad"

# Valor que un administrador escribe de verdad cuando cree que el campo son
# minutos o segundos. En «Horas de bloqueo» desborda el `now() - timedelta(...)`
# de axes: no es un número de laboratorio.
VALOR_ABSURDO = 999999999


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

    def test_el_formulario_rechaza_los_valores_por_encima_del_tope(self):
        """Capa 1: el máximo también es política, no solo el mínimo.

        Sin tope, «Horas de bloqueo» acepta un número que desborda el
        `now() - timedelta(...)` de axes y deja el login en 500 para todos.
        """
        for campo, valor in (
            ("sesion_minutos", SESION_MINUTOS_MAXIMO + 1),
            ("intentos_antes_de_bloquear", INTENTOS_MAXIMO + 1),
            ("horas_de_bloqueo", HORAS_DE_BLOQUEO_MAXIMO + 1),
            ("longitud_minima_password", LONGITUD_MINIMA_MAXIMA + 1),
        ):
            with self.subTest(campo=campo):
                antes = getattr(ConfiguracionSistema.objects.get(pk=1), campo)
                form = self._form(**{campo: valor})
                self.assertFalse(form.is_valid())
                self.assertIn(campo, form.errors)
                self.assertEqual(
                    getattr(ConfiguracionSistema.objects.get(pk=1), campo), antes
                )

    def test_el_formulario_acepta_los_valores_justo_en_el_tope(self):
        """Contraprueba: el tope es el último valor válido, no el primero inválido."""
        for campo, valor in (
            ("sesion_minutos", SESION_MINUTOS_MAXIMO),
            ("intentos_antes_de_bloquear", INTENTOS_MAXIMO),
            ("horas_de_bloqueo", HORAS_DE_BLOQUEO_MAXIMO),
            ("longitud_minima_password", LONGITUD_MINIMA_MAXIMA),
        ):
            with self.subTest(campo=campo):
                form = self._form(**{campo: valor})
                self.assertTrue(form.is_valid(), form.errors)

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


class PoliticaAcotadaAlLeerTests(TestCase):
    """Capa 2: el resolvedor no se fía de la columna, acota lo que lee.

    Un ``MaxValueValidator`` en el campo no cierra el agujero por sí solo:
    ``queryset.update()`` y un ``UPDATE`` por SQL se saltan los validadores
    igual que se saltan ``save()``. Es el mismo principio que ya usa
    ``modulos_activos()`` con ``MODULOS_ESENCIALES`` y ``nivel_permiso`` con el
    superadministrador: la decisión no sale del dato.

    Todas las escrituras de aquí van por ``update()`` a propósito.
    """

    def setUp(self):
        _config()

    def test_los_topes_del_resolvedor_coinciden_con_los_del_modelo(self):
        """Si se separan, el formulario y el resolvedor dirían cosas distintas."""
        from django.core.validators import MaxValueValidator

        esperado = {
            "sesion_minutos": SESION_MINUTOS_MAXIMO,
            "intentos_antes_de_bloquear": INTENTOS_MAXIMO,
            "horas_de_bloqueo": HORAS_DE_BLOQUEO_MAXIMO,
            "longitud_minima_password": LONGITUD_MINIMA_MAXIMA,
        }
        for campo, tope in esperado.items():
            with self.subTest(campo=campo):
                maximos = [
                    v.limit_value
                    for v in ConfiguracionSistema._meta.get_field(campo).validators
                    if isinstance(v, MaxValueValidator)
                ]
                self.assertEqual(maximos, [tope])

    def test_unas_horas_de_bloqueo_desbordantes_caen_al_tope(self):
        _config(horas_de_bloqueo=VALOR_ABSURDO)
        with self.assertLogs("administracion.seguridad", level="WARNING"):
            self.assertEqual(
                tiempo_de_bloqueo(None), timedelta(hours=HORAS_DE_BLOQUEO_MAXIMO)
            )

    def test_un_limite_de_intentos_absurdo_cae_al_tope(self):
        """Sin tope, axes no bloquea nunca: fuerza bruta sin freno y en silencio."""
        _config(intentos_antes_de_bloquear=VALOR_ABSURDO)
        with self.assertLogs("administracion.seguridad", level="WARNING"):
            self.assertEqual(limite_de_intentos(None, {}), INTENTOS_MAXIMO)

    def test_unos_minutos_de_sesion_absurdos_caen_al_tope(self):
        _config(sesion_minutos=VALOR_ABSURDO)
        with self.assertLogs("administracion.seguridad", level="WARNING"):
            self.assertEqual(minutos_de_sesion(), SESION_MINUTOS_MAXIMO)

    def test_una_longitud_minima_absurda_cae_al_tope(self):
        """Sin tope no se puede crear ni resetear ninguna contraseña."""
        _config(longitud_minima_password=VALOR_ABSURDO)
        with self.assertLogs("administracion.seguridad", level="WARNING"):
            self.assertEqual(
                LongitudMinimaConfigurable().longitud_minima(), LONGITUD_MINIMA_MAXIMA
            )

    def test_un_valor_por_debajo_del_minimo_tambien_se_acota(self):
        """Un 0 en sesión o en intentos llega por la misma puerta que el máximo."""
        _config(sesion_minutos=0, intentos_antes_de_bloquear=0, longitud_minima_password=1)
        with self.assertLogs("administracion.seguridad", level="WARNING"):
            self.assertEqual(minutos_de_sesion(), 1)
            self.assertEqual(limite_de_intentos(None, {}), 1)
            self.assertEqual(LongitudMinimaConfigurable().longitud_minima(), 8)

    def test_los_valores_razonables_de_siempre_pasan_intactos(self):
        """Contraprueba: acotar no puede cambiar la política de una instalación."""
        _config(
            sesion_minutos=30,
            intentos_antes_de_bloquear=5,
            horas_de_bloqueo=1,
            longitud_minima_password=10,
        )
        self.assertEqual(minutos_de_sesion(), 30)
        self.assertEqual(limite_de_intentos(None, {}), 5)
        self.assertEqual(tiempo_de_bloqueo(None), timedelta(hours=1))
        self.assertEqual(LongitudMinimaConfigurable().longitud_minima(), 10)

    def test_cero_horas_de_bloqueo_sigue_siendo_un_bloqueo_que_no_caduca(self):
        """El mínimo de este campo es 0 y significa algo: acotar no lo puede comer."""
        _config(horas_de_bloqueo=0)
        bloqueo = tiempo_de_bloqueo(None)
        self.assertIsNotNone(bloqueo)
        self.assertGreater(bloqueo, timedelta(days=365 * 10))

    def test_una_interfaceerror_tampoco_tumba_la_lectura(self):
        """``InterfaceError`` hereda de ``django.db.Error``, NO de ``DatabaseError``.

        Es el «connection already closed» de psycopg y solo muerde en
        PostgreSQL, que es producción. Sube desde ``limite_de_intentos`` (500 en
        el login) y desde ``minutos_de_sesion`` (500 en cada petición
        autenticada).
        """
        from django.db import InterfaceError

        fallo = mock.patch.object(
            ConfiguracionSistema,
            "get_config",
            side_effect=InterfaceError("connection already closed"),
        )
        with fallo, self.assertLogs("administracion.seguridad", level="WARNING"):
            self.assertEqual(limite_de_intentos(None, {}), INTENTOS_POR_DEFECTO)
            self.assertEqual(
                tiempo_de_bloqueo(None), timedelta(hours=HORAS_DE_BLOQUEO_POR_DEFECTO)
            )
            self.assertEqual(minutos_de_sesion(), settings.SESSION_COOKIE_AGE // 60)
            self.assertEqual(
                LongitudMinimaConfigurable().longitud_minima(),
                LongitudMinimaConfigurable().min_length,
            )


class GuardarLaConfiguracionValidaTests(TestCase):
    """``ConfiguracionSistema.save()`` llama a ``full_clean()``.

    Cierra el camino del ``obj.save()`` —un comando de gestión, el shell, una
    importación—, que ni el formulario ni el resolvedor cubren. No cierra el del
    ``queryset.update()``: de ese se encarga ``administracion.seguridad``.
    """

    def test_un_valor_fuera_de_rango_no_se_puede_guardar_por_instancia(self):
        config = ConfiguracionSistema.get_config()
        config.horas_de_bloqueo = VALOR_ABSURDO
        with self.assertRaises(ValidationError) as caja:
            config.save()
        self.assertIn("horas_de_bloqueo", caja.exception.message_dict)
        self.assertEqual(ConfiguracionSistema.objects.get(pk=1).horas_de_bloqueo, 1)

    def test_los_valores_de_siempre_se_siguen_guardando(self):
        """Contraprueba: el ``full_clean()`` no puede estorbar a un guardado sano."""
        config = ConfiguracionSistema.get_config()
        config.nombre_empresa = "Clinica X"
        config.sesion_minutos = 45
        config.save()
        guardada = ConfiguracionSistema.objects.get(pk=1)
        self.assertEqual(guardada.nombre_empresa, "Clinica X")
        self.assertEqual(guardada.sesion_minutos, 45)

    def test_la_migracion_acota_lo_que_ya_estuviera_guardado(self):
        """Un ``AlterField`` no revisa los datos: la fila heredada se queda.

        Y con el ``full_clean()`` del ``save()``, una fila fuera de rango haría
        fallar el guardado de pantallas que ni muestran ese campo. Por eso la
        0013 acota antes de alterar los campos.
        """
        from importlib import import_module

        from django.apps import apps as registro_de_apps

        migracion = import_module(
            "administracion.migrations.0013_topes_politica_seguridad"
        )
        _config(
            sesion_minutos=VALOR_ABSURDO,
            intentos_antes_de_bloquear=VALOR_ABSURDO,
            horas_de_bloqueo=VALOR_ABSURDO,
            longitud_minima_password=VALOR_ABSURDO,
        )

        migracion.acotar_lo_guardado(registro_de_apps, None)

        config = ConfiguracionSistema.objects.get(pk=1)
        self.assertEqual(config.sesion_minutos, SESION_MINUTOS_MAXIMO)
        self.assertEqual(config.intentos_antes_de_bloquear, INTENTOS_MAXIMO)
        self.assertEqual(config.horas_de_bloqueo, HORAS_DE_BLOQUEO_MAXIMO)
        self.assertEqual(config.longitud_minima_password, LONGITUD_MINIMA_MAXIMA)
        # Y ahora la fila se puede guardar: era justo lo que la 0013 evita.
        config.nombre_empresa = "Clinica X"
        config.save()

    def test_la_migracion_no_toca_una_fila_sana(self):
        from importlib import import_module

        from django.apps import apps as registro_de_apps

        migracion = import_module(
            "administracion.migrations.0013_topes_politica_seguridad"
        )
        _config()

        migracion.acotar_lo_guardado(registro_de_apps, None)

        config = ConfiguracionSistema.objects.get(pk=1)
        self.assertEqual(config.sesion_minutos, 30)
        self.assertEqual(config.intentos_antes_de_bloquear, 5)
        self.assertEqual(config.horas_de_bloqueo, 1)
        self.assertEqual(config.longitud_minima_password, 10)


class LoginConValoresDesbordantesTests(TestCase):
    """La prueba del crítico: ningún valor guardado deja el login en 500.

    Con «Horas de bloqueo» grande la cadena es
    ``axes/backends.py`` → ``is_allowed`` → ``is_locked`` → ``get_failures`` →
    ``get_user_attempts`` → ``axes/attempts.py:get_cool_off_threshold`` →
    ``now() - timedelta(hours=horas)``, que lanza ``OverflowError``. No es
    ``PermissionDenied``, así que ni ``authenticate()`` ni el middleware de axes
    lo atrapan: 500 en cada intento de login, para todas las cuentas y también
    en ``/admin/login/``. La recuperación por la web no sirve, porque exige
    poder entrar.
    """

    LOGIN = "/accounts/login/"

    def setUp(self):
        from axes.models import AccessAttempt, AccessFailureLog

        AccessAttempt.objects.all().delete()
        AccessFailureLog.objects.all().delete()
        _config()
        self.usuario = get_user_model().objects.create_user(
            username="seg_tope", password=CLAVE_BUENA, rol="tecnico"
        )

    def _intento_fallido(self):
        return self.client.post(
            self.LOGIN, {"username": "seg_tope", "password": "password-incorrecta"}
        )

    def test_con_horas_de_bloqueo_desbordantes_el_login_sigue_respondiendo(self):
        _config(horas_de_bloqueo=VALOR_ABSURDO, intentos_antes_de_bloquear=2)
        self.assertEqual(self._intento_fallido().status_code, 200)
        self.assertEqual(self._intento_fallido().status_code, 429)

    def test_con_horas_de_bloqueo_desbordantes_tambien_entra_quien_acierta(self):
        """No basta con «no 500»: la política acotada tiene que dejar entrar."""
        _config(horas_de_bloqueo=VALOR_ABSURDO)
        resp = self.client.post(
            self.LOGIN, {"username": "seg_tope", "password": CLAVE_BUENA}
        )
        self.assertRedirects(resp, reverse("core:dashboard"))

    def test_con_un_limite_de_intentos_absurdo_axes_sigue_teniendo_un_limite(self):
        from axes.helpers import get_failure_limit

        _config(intentos_antes_de_bloquear=VALOR_ABSURDO)
        self.assertEqual(self._intento_fallido().status_code, 200)
        self.assertEqual(get_failure_limit(None, {}), INTENTOS_MAXIMO)

    def test_con_minutos_de_sesion_desbordantes_la_peticion_responde(self):
        """``set_expiry(minutos * 60)`` desborda al guardar la sesión: 500 en
        CADA petición autenticada, con ``SESSION_SAVE_EVERY_REQUEST`` activo."""
        self.client.force_login(self.usuario)
        _config(sesion_minutos=VALOR_ABSURDO)
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)
        self.assertEqual(self.client.session.get_expiry_age(), SESION_MINUTOS_MAXIMO * 60)
