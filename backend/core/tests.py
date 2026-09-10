from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

CustomUser = get_user_model()


def _user(rol):
    return CustomUser.objects.create_user(
        username=f"core_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


class DashboardTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp.url)

    def test_status_200(self):
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_context_variables(self):
        resp = self.client.get(reverse("core:dashboard"))
        for key in (
            "total_usuarios",
            "total_activos",
            "activos_asignados",
            "activos_disponibles",
            "activos_baja",
            "ordenes_abiertas",
            "ordenes_atrasadas",
        ):
            self.assertIn(key, resp.context)
