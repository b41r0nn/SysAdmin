from django.contrib.auth import get_user_model
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