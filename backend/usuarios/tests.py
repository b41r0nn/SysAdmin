from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from usuarios.models import Usuario

CustomUser = get_user_model()


def _user(rol):
    return CustomUser.objects.create_user(
        username=f"usr_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


def _persona(**kw):
    defaults = {
        "nombre_completo": "Test User",
        "documento_identidad": "12345",
        "cargo": "Tecnico",
        "area": "TI",
        "correo": "t@test.com",
    }
    defaults.update(kw)
    return Usuario.objects.create(**defaults)


class UsuariosLoginTests(TestCase):
    def test_lista_requiere_login(self):
        resp = self.client.get(reverse("usuarios:lista"))
        self.assertEqual(resp.status_code, 302)

    def test_detalle_requiere_login(self):
        u = _persona()
        resp = self.client.get(reverse("usuarios:detalle", args=[u.pk]))
        self.assertEqual(resp.status_code, 302)


class UsuariosCRUDTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_lista_returns_200(self):
        resp = self.client.get(reverse("usuarios:lista"))
        self.assertEqual(resp.status_code, 200)

    def test_detalle_returns_200(self):
        u = _persona()
        resp = self.client.get(reverse("usuarios:detalle", args=[u.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_crear_get(self):
        resp = self.client.get(reverse("usuarios:crear"))
        self.assertEqual(resp.status_code, 200)

    def test_crear_post(self):
        resp = self.client.post(
            reverse("usuarios:crear"),
            {
                "nombre_completo": "Nuevo Usuario",
                "documento_identidad": "99999",
                "cargo": "Analista",
                "area": "Sistemas",
                "correo": "n@test.com",
                "estado": "activo",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Usuario.objects.filter(documento_identidad="99999").exists())

    def test_editar_get(self):
        u = _persona()
        resp = self.client.get(reverse("usuarios:editar", args=[u.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_editar_post(self):
        u = _persona()
        resp = self.client.post(
            reverse("usuarios:editar", args=[u.pk]),
            {
                "nombre_completo": "Editado",
                "documento_identidad": u.documento_identidad,
                "cargo": "Gerente",
                "area": "Direccion",
                "correo": u.correo,
                "estado": "activo",
            },
        )
        self.assertEqual(resp.status_code, 302)
        u.refresh_from_db()
        self.assertEqual(u.nombre_completo, "Editado")

    def test_toggle_estado(self):
        u = _persona()
        self.assertTrue(u.is_activo)
        resp = self.client.post(reverse("usuarios:toggle_estado", args=[u.pk]))
        self.assertEqual(resp.status_code, 302)
        u.refresh_from_db()
        self.assertFalse(u.is_activo)

    def test_plantilla_excel_returns_xlsx(self):
        resp = self.client.get(reverse("usuarios:importar_plantilla"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])


class UsuariosPermisosTests(TestCase):
    def test_lectura_no_puede_crear(self):
        user = _user("lectura")
        self.client.force_login(user)
        resp = self.client.get(reverse("usuarios:crear"))
        self.assertEqual(resp.status_code, 302)

    def test_tecnico_puede_ver_lista(self):
        user = _user("tecnico")
        self.client.force_login(user)
        resp = self.client.get(reverse("usuarios:lista"))
        self.assertEqual(resp.status_code, 200)
