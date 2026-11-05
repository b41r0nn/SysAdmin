from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from accounts.permisos import PERMISOS_POR_ROL
from administracion.registro import invalidar_cache

CustomUser = get_user_model()


def crear_usuario(rol, username=None, **kwargs):
    return CustomUser.objects.create_user(
        username=username or f"user_{rol}_{CustomUser.objects.count()}",
        password="testpass123",
        rol=rol,
        **kwargs,
    )


class RequierePermisoTests(TestCase):
    def login_como(self, rol):
        usuario = crear_usuario(rol)
        self.client.force_login(usuario)
        return usuario

    def test_matriz_cubre_todos_los_roles_modulos(self):
        """La matriz del código ya no es la fuente de verdad, pero sigue siendo
        el respaldo de una base vacía: un hueco ahí daría «ninguno» por sorpresa
        justo cuando la tabla no se puede leer. Lo que la tabla sembrada
        reproduce esta matriz lo prueba administracion.test_roles.
        """
        roles = dict(CustomUser.ROL_CHOICES).keys()
        for rol in roles:
            self.assertIn(rol, PERMISOS_POR_ROL, f"Falta rol {rol} en la matriz")
            self.assertEqual(
                set(PERMISOS_POR_ROL[rol].keys()),
                set(PERMISOS_POR_ROL["superadmin"].keys()),
                f"Módulos distintos en rol {rol}",
            )

    def test_no_autenticado_redirige_a_login(self):
        response = self.client.get(reverse("usuarios:lista"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_tecnico_puede_leer_usuarios(self):
        self.login_como("tecnico")
        response = self.client.get(reverse("usuarios:lista"))
        self.assertEqual(response.status_code, 200)

    def test_tecnico_no_puede_acceder_passwords(self):
        self.login_como("tecnico")
        response = self.client.get(reverse("passwords:index"))
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_tecnico_no_puede_escribir_usuarios(self):
        self.login_como("tecnico")
        response = self.client.get(reverse("usuarios:crear"))
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_admin_puede_leer_pero_no_escribir_passwords(self):
        self.login_como("admin")
        response = self.client.get(reverse("passwords:index"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("passwords:vault_crear"))
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_solo_superadmin_accede_administracion(self):
        admin = self.login_como("admin")
        response = self.client.get(reverse("administracion:lista_auditoria"))
        self.assertRedirects(response, reverse("core:dashboard"))

        self.client.force_login(crear_usuario("superadmin", username="super_t"))
        response = self.client.get(reverse("administracion:lista_auditoria"))
        self.assertEqual(response.status_code, 200)

        self.assertNotEqual(admin.rol, "superadmin")

    def test_superadmin_accede_todo(self):
        self.login_como("superadmin")
        for url in [
            reverse("usuarios:crear"),
            reverse("inventario:crear"),
            reverse("mantenimiento:nuevo"),
            reverse("passwords:vault_crear"),
            reverse("administracion:configuracion"),
            reverse("documentos:crear"),
        ]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"Superadmin sin acceso a {url}")

    def test_superuser_con_rol_tecnico_accede_administracion(self):
        """Bypass por is_superuser: un superuser creado tras la migración (rol default
        'tecnico') debe tener acceso completo sin depender de que le seteen rol a mano."""
        superuser = CustomUser.objects.create_superuser(
            username="root_futuro",
            password="testpass123",
            rol="tecnico",
        )
        self.client.force_login(superuser)
        response = self.client.get(reverse("administracion:lista_auditoria"))
        self.assertEqual(response.status_code, 200)


class RequierePermisoHtmxTests(TestCase):
    """Una petición de HTMX sin permiso responde 403; una navegación normal, no.

    Con un 302, HTMX sigue la redirección de forma transparente y acaba
    intercambiando el HTML completo del tablero —o del formulario de login, si
    la sesión caducó— dentro del ``<tr>`` o el ``<td>`` que disparó la petición.
    Con un 4xx no intercambia nada, y el manejador de ``htmx:responseError`` del
    JS es el que avisa en pantalla.
    """

    def setUp(self):
        # La caché de permisos sobrevive al rollback de cada prueba.
        invalidar_cache()
        self.addCleanup(invalidar_cache)

    def test_sin_sesion_una_peticion_de_htmx_recibe_403_sin_el_login(self):
        """El disparador universal: la sesión caduca por inactividad.

        ``login_required`` envuelve a la envoltura del decorador, así que corre
        ANTES de su cuerpo y este caso NUNCA llega a la rama de permisos. Un 403
        puesto solo en esa rama dejaría el bug principal abierto: aquí seguiría
        llegando el formulario de login metido en una celda de la tabla.
        """
        for url in (
            reverse("administracion:toggle_modulo", args=["soporte"]),
            reverse("administracion:guardar_permiso", args=["tecnico", "documentos"]),
        ):
            with self.subTest(url=url):
                resp = self.client.post(url, {"nivel": "escritura"}, HTTP_HX_REQUEST="true")
                self.assertEqual(resp.status_code, 403)
                cuerpo = resp.content.decode()
                self.assertNotIn("<form", cuerpo)
                self.assertNotIn("csrfmiddlewaretoken", cuerpo)
                self.assertNotIn("password", cuerpo)

    def test_sin_sesion_y_sin_la_cabecera_de_htmx_sigue_yendo_al_login(self):
        """Regresión: una navegación normal no cambia."""
        resp = self.client.get(reverse("administracion:modulos"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp.url)

    def test_el_403_lleva_el_motivo_en_espanol(self):
        """El cuerpo del 403 es lo que el manejador del JS muestra en pantalla."""
        self.client.force_login(crear_usuario("tecnico"))
        resp = self.client.post(
            reverse("administracion:toggle_modulo", args=["soporte"]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("permiso", resp.content.decode().lower())

    def test_una_lectura_por_htmx_sin_permiso_tambien_es_403(self):
        """No es solo cosa del POST: la pantalla de cuentas se recarga por HTMX."""
        self.client.force_login(crear_usuario("tecnico"))
        resp = self.client.get(reverse("administracion:cuentas"), HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 403)

    def test_con_sesion_y_sin_htmx_sigue_redirigiendo_al_tablero(self):
        """Regresión: el mensaje y la redirección de hoy no se tocan."""
        self.client.force_login(crear_usuario("tecnico"))
        resp = self.client.get(reverse("administracion:modulos"))
        self.assertRedirects(resp, reverse("core:dashboard"))


class PermisosExtrasTagTests(TestCase):
    def _render(self, rol, modulo, nivel="lectura"):
        usuario = crear_usuario(rol)
        template = Template(
            "{% load permisos_extras %}"
            "{% tiene_permiso modulo nivel as perm %}"
            "{% if perm %}SI{% else %}NO{% endif %}"
        )
        return template.render(Context({"user": usuario, "modulo": modulo, "nivel": nivel}))

    def test_tag_por_rol(self):
        self.assertEqual(self._render("superadmin", "administracion", "escritura"), "SI")
        self.assertEqual(self._render("admin", "administracion"), "NO")
        self.assertEqual(self._render("admin", "passwords", "escritura"), "NO")
        self.assertEqual(self._render("tecnico", "inventario", "escritura"), "SI")
        self.assertEqual(self._render("lectura", "inventario", "escritura"), "NO")
        self.assertEqual(self._render("lectura", "reportes", "lectura"), "SI")

    def test_tag_con_usuario_no_autenticado(self):
        template = Template(
            "{% load permisos_extras %}"
            "{% tiene_permiso modulo nivel as perm %}"
            "{% if perm %}SI{% else %}NO{% endif %}"
        )
        self.assertEqual(
            template.render(Context({"user": None, "modulo": "usuarios", "nivel": "lectura"})),
            "NO",
        )


class LoginSeguridadTests(TestCase):
    """Endurecimiento del login: mensajes genéricos, axes y auditoría."""

    LOGIN_URL_PATH = "/accounts/login/"

    def setUp(self):
        from axes.models import AccessAttempt, AccessFailureLog

        AccessAttempt.objects.all().delete()
        AccessFailureLog.objects.all().delete()
        self.usuario = crear_usuario("tecnico", username="seg_login")

    def _intentar_login(self, username="seg_login", password="password-incorrecta", ip=None):
        extra = {"HTTP_X_FORWARDED_FOR": ip} if ip else {}
        return self.client.post(
            self.LOGIN_URL_PATH,
            {"username": username, "password": password},
            **extra,
        )

    def test_mensaje_error_generico_usuario_inexistente(self):
        resp = self._intentar_login(username="no_existe")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Usuario o contraseña incorrectos.")

    def test_mensaje_error_generico_password_mala(self):
        resp = self._intentar_login()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Usuario o contraseña incorrectos.")

    def test_mensaje_generico_no_revela_existencia(self):
        resp_inexistente = self._intentar_login(username="no_existe")
        resp_mala_clave = self._intentar_login()
        for resp in (resp_inexistente, resp_mala_clave):
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "Usuario o contraseña incorrectos.")
            self.assertNotContains(resp, "no existe")
            self.assertNotContains(resp, "no está registrado")

    def test_cinco_intentos_fallidos_registran_lockout_en_bd(self):
        from axes.models import AccessAttempt

        for _ in range(5):
            self._intentar_login()
            self.assertLess(AccessAttempt.objects.filter(username="seg_login").count(), 6)

        self.assertFalse(
            CustomUser.objects.filter(username="seg_login").exclude(is_active=True).exists()
        )

    def test_login_bloqueado_devuelve_429(self):
        for _ in range(5):
            self._intentar_login()
        resp = self._intentar_login()
        self.assertEqual(resp.status_code, 429)

    def test_bloqueo_crea_registros_auditoria(self):
        from administracion.models import RegistroAuditoria

        for _ in range(5):
            self._intentar_login()
        self._intentar_login()

        fallidos = RegistroAuditoria.objects.filter(accion="login_fallido")
        bloqueos = RegistroAuditoria.objects.filter(accion="cuenta_bloqueada")
        self.assertGreaterEqual(fallidos.count(), 5)
        self.assertGreaterEqual(bloqueos.count(), 1)
        self.assertEqual(bloqueos.first().modulo, "auth")

    def test_axes_usa_ip_de_forwarded_for(self):
        from axes.models import AccessAttempt

        self._intentar_login(ip="10.0.0.5")
        intento = AccessAttempt.objects.get(username="seg_login")
        self.assertEqual(intento.ip_address, "10.0.0.5")

    def test_bloqueo_es_por_usuario_e_ip(self):
        for _ in range(5):
            self._intentar_login(ip="10.0.0.5")
        # La combinación (usuario, 10.0.0.5) está bloqueada, pero otra IP no.
        resp_otro = self.client.post(
            self.LOGIN_URL_PATH,
            {"username": "seg_login", "password": "testpass123"},
            HTTP_X_FORWARDED_FOR="10.0.0.6",
        )
        self.assertRedirects(resp_otro, reverse("core:dashboard"))

    def test_auditoria_login_fallido_guarda_ip_real(self):
        from administracion.models import RegistroAuditoria

        self._intentar_login(ip="9.9.9.9, 10.0.0.5")
        registro = RegistroAuditoria.objects.filter(accion="login_fallido").first()
        self.assertEqual(registro.ip, "10.0.0.5")

    def test_login_exitoso_resetea_contador(self):
        from axes.models import AccessAttempt

        self._intentar_login()
        self._intentar_login()
        self._intentar_login()

        resp = self.client.post(
            self.LOGIN_URL_PATH,
            {"username": "seg_login", "password": "testpass123"},
        )
        self.assertRedirects(resp, reverse("core:dashboard"))
        self.assertEqual(AccessAttempt.objects.filter(username="seg_login").count(), 0)

    def test_cookies_sesion_seguras(self):
        from django.conf import settings

        self.client.post(
            self.LOGIN_URL_PATH,
            {"username": "seg_login", "password": "testpass123"},
        )
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertGreaterEqual(settings.SESSION_COOKIE_AGE, 60)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)

    def test_sesion_se_renueva_con_actividad(self):
        from django.contrib.sessions.models import Session

        self.client.force_login(self.usuario)
        antes = Session.objects.get().expire_date
        self.client.get(reverse("core:dashboard"))
        despues = Session.objects.get().expire_date
        self.assertGreater(despues, antes)

    def test_headers_seguridad_presentes(self):
        resp = self.client.get(self.LOGIN_URL_PATH)
        self.assertEqual(resp.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.get("X-Frame-Options"), "DENY")
        self.assertEqual(resp.get("Referrer-Policy"), "same-origin")

    def test_axes_configuracion_activa(self):
        from axes.helpers import get_failure_limit
        from django.conf import settings

        # El límite ya no es el entero 5 en los settings: es la ruta con puntos
        # de administracion.seguridad.limite_de_intentos, que lo lee de
        # ConfiguracionSistema. Se comprueba el límite EFECTIVO, resolviéndolo
        # como lo resuelve axes, que es lo que esta prueba siempre quiso decir.
        self.assertEqual(get_failure_limit(None, {}), 5)
        self.assertEqual(settings.AXES_LOCKOUT_PARAMETERS, [["username", "ip_address"]])
        self.assertTrue(settings.AXES_RESET_ON_SUCCESS)
        self.assertIn(
            "axes.backends.AxesStandaloneBackend",
            settings.AUTHENTICATION_BACKENDS,
        )

    def test_password_validators_min_length_10(self):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            validate_password("corta123", user=self.usuario)
        validate_password("clavelargadeseguridad", user=self.usuario)
