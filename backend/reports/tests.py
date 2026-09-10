from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

CustomUser = get_user_model()


class _FakeHTML:
    def __init__(self, *args, **kwargs):
        pass

    def write_pdf(self, *args, **kwargs):
        return b"%PDF-1.4 fake"


class _FakeWeasyprint:
    HTML = _FakeHTML


def _fake_weasyprint():
    return _FakeWeasyprint()


def _user(rol):
    return CustomUser.objects.create_user(
        username=f"rpt_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


class ReportsLoginTests(TestCase):
    def test_index_requiere_login(self):
        resp = self.client.get(reverse("reports:index"))
        self.assertEqual(resp.status_code, 302)


class ReportsIndexTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_index_returns_200(self):
        resp = self.client.get(reverse("reports:index"))
        self.assertEqual(resp.status_code, 200)


class ReportsExcelTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_inventario_excel(self):
        resp = self.client.get(reverse("reports:inventario_excel"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])

    def test_usuarios_excel(self):
        resp = self.client.get(reverse("reports:usuarios_excel"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])

    def test_movimientos_excel(self):
        resp = self.client.get(reverse("reports:movimientos_excel"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])

    def test_costos_excel(self):
        resp = self.client.get(reverse("reports:costos_excel"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])

    def test_mantenimiento_excel(self):
        resp = self.client.get(reverse("reports:mantenimiento_excel"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])


class ReportsPDFTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_inventario_pdf(self):
        with patch.dict(
            "sys.modules",
            {
                "weasyprint": _fake_weasyprint(),
                "weasyprint.HTML": _fake_weasyprint().HTML,
            },
        ):
            resp = self.client.get(reverse("reports:inventario_pdf"))
        self.assertEqual(resp.status_code, 200)

    def test_usuarios_pdf(self):
        with patch.dict(
            "sys.modules",
            {
                "weasyprint": _fake_weasyprint(),
                "weasyprint.HTML": _fake_weasyprint().HTML,
            },
        ):
            resp = self.client.get(reverse("reports:usuarios_pdf"))
        self.assertEqual(resp.status_code, 200)


class ReportsPermisosTests(TestCase):
    def test_tecnico_puede_ver_index(self):
        user = _user("tecnico")
        self.client.force_login(user)
        resp = self.client.get(reverse("reports:index"))
        self.assertEqual(resp.status_code, 200)
