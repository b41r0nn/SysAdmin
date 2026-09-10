from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventario.models import Activo
from licencias.models import LicenciaSoftware

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
        username=f"lic_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


def _activo(serial="SN-LIC-001"):
    return Activo.objects.create(
        serial=serial,
        tipo_dispositivo="escritorio",
        marca="HP",
        modelo="Pro",
        estado="disponible",
    )


def _licencia(**kw):
    defaults = {"nombre": "Microsoft 365", "clave": "XXXX-XXXX-XXXX"}
    defaults.update(kw)
    return LicenciaSoftware.objects.create(**defaults)


# ─── Acceso ────────────────────────────────────────────────────────


class LicenciasLoginTests(TestCase):
    def test_lista_requiere_login(self):
        resp = self.client.get(reverse("licencias:lista"))
        self.assertEqual(resp.status_code, 302)

    def test_exportar_pdf_requiere_login(self):
        resp = self.client.get(reverse("licencias:exportar_pdf"))
        self.assertEqual(resp.status_code, 302)


# ─── CRUD ──────────────────────────────────────────────────────────


class LicenciasCRUDTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_lista_returns_200(self):
        _licencia()
        resp = self.client.get(reverse("licencias:lista"))
        self.assertEqual(resp.status_code, 200)

    def test_crear_licencia_post(self):
        resp = self.client.post(
            reverse("licencias:crear"),
            {
                "nombre": "Antivirus X",
                "tipo": "volumen",
                "cantidad": "10",
                "clave": "AV-123",
                "estado": "activa",
            },
        )
        self.assertEqual(resp.status_code, 302)
        licencia = LicenciaSoftware.objects.get(nombre="Antivirus X")
        self.assertEqual(licencia.cantidad, 10)

    def test_editar_licencia(self):
        licencia = _licencia(nombre="Windows Server")
        resp = self.client.post(
            reverse("licencias:editar", args=[licencia.pk]),
            {
                "nombre": "Windows Server 2022",
                "tipo": "oem",
                "cantidad": "1",
                "estado": "cancelada",
            },
        )
        self.assertEqual(resp.status_code, 302)
        licencia.refresh_from_db()
        self.assertEqual(licencia.nombre, "Windows Server 2022")
        self.assertEqual(licencia.estado, "cancelada")

    def test_detalle_returns_200(self):
        licencia = _licencia()
        licencia.activos.add(self.activo)
        resp = self.client.get(reverse("licencias:detalle", args=[licencia.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.activo.serial)


# ─── Estado efectivo y vencimiento ─────────────────────────────────


class EstadoEfectivoTests(TestCase):
    def test_sin_vencimiento_es_activa(self):
        licencia = _licencia()
        self.assertEqual(licencia.estado_efectivo, "activa")

    def test_vencida_en_pasado(self):
        licencia = _licencia(fecha_vencimiento=date.today() - timedelta(days=1))
        self.assertEqual(licencia.estado_efectivo, "vencida")

    def test_por_vencer_en_7_dias(self):
        licencia = _licencia(fecha_vencimiento=date.today() + timedelta(days=7))
        self.assertEqual(licencia.estado_efectivo, "por_vencer")

    def test_cancelada_se_mantiene(self):
        licencia = _licencia(estado="cancelada", fecha_vencimiento=date.today() - timedelta(days=5))
        self.assertEqual(licencia.estado_efectivo, "cancelada")

    def test_filtro_por_estado_efectivo_en_lista(self):
        _licencia(nombre="OK", fecha_vencimiento=None)
        _licencia(nombre="Vencida", fecha_vencimiento=date.today() - timedelta(days=3))

        user = _user("superadmin")
        self.client = Client()
        self.client.force_login(user)

        resp = self.client.get(reverse("licencias:lista"), {"estado": "vencida"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Vencida")
        self.assertNotContains(resp, "OK")


# ─── Permisos por rol ──────────────────────────────────────────────


class LicenciasPermisosTests(TestCase):
    def setUp(self):
        self.user = _user("lectura")
        self.client = Client()
        self.client.force_login(self.user)
        self.licencia = _licencia()

    def test_lectura_puede_ver_lista(self):
        resp = self.client.get(reverse("licencias:lista"))
        self.assertEqual(resp.status_code, 200)

    def test_lectura_no_puede_crear(self):
        resp = self.client.get(reverse("licencias:crear"))
        self.assertEqual(resp.status_code, 302)

    def test_lectura_no_puede_editar(self):
        resp = self.client.get(reverse("licencias:editar", args=[self.licencia.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_lectura_no_puede_eliminar(self):
        resp = self.client.get(reverse("licencias:eliminar", args=[self.licencia.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_tecnico_puede_leer_pero_no_crear(self):
        tecnico = _user("tecnico")
        self.client.force_login(tecnico)
        resp = self.client.get(reverse("licencias:lista"))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse("licencias:crear"))
        self.assertEqual(resp.status_code, 302)


# ─── Exportación ───────────────────────────────────────────────────


class ExportarLicenciasTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        _licencia(nombre="Office 2021", clave="OF-1", costo="500000")
        _licencia(nombre="Adobe CC", clave="AD-2")

    def test_exportar_excel(self):
        resp = self.client.get(reverse("licencias:exportar_excel"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("licencias.xlsx", resp["Content-Disposition"])

    def test_exportar_pdf(self):
        with patch.dict(
            "sys.modules",
            {
                "weasyprint": _fake_weasyprint(),
                "weasyprint.HTML": _fake_weasyprint().HTML,
            },
        ):
            resp = self.client.get(reverse("licencias:exportar_pdf"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("reporte_licencias.pdf", resp["Content-Disposition"])

    def test_eliminar_licencia(self):
        licencia = _licencia(nombre="A borrar")
        resp = self.client.post(reverse("licencias:eliminar", args=[licencia.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(LicenciaSoftware.objects.filter(pk=licencia.pk).exists())