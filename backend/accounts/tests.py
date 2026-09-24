from django.contrib.auth import get_user_model
from django.test import override_settings
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from accounts.permisos import PERMISOS_POR_ROL

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
            reverse("mantenimiento:crear_plan"),
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

    def _intentar_login(self, username="seg_login", password="password-incorrecta"):
        return self.client.post(
            self.LOGIN_URL_PATH,
            {"username": username, "password": password},
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
        self.assertEqual(settings.SESSION_COOKIE_AGE, 28800)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)

    def test_headers_seguridad_presentes(self):
        resp = self.client.get(self.LOGIN_URL_PATH)
        self.assertEqual(resp.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.get("X-Frame-Options"), "DENY")
        self.assertEqual(resp.get("Referrer-Policy"), "same-origin")

    def test_axes_configuracion_activa(self):
        from django.conf import settings

        self.assertTrue(settings.AXES_FAILURE_LIMIT == 5)
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