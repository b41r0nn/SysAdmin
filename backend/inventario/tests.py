from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.template.loader import render_to_string
from django.urls import reverse

from inventario.models import Activo
from inventario.views import _etiqueta_context

CustomUser = get_user_model()


class FakeWeasyHTML:
    def __init__(self, *args, **kwargs):
        pass

    def write_pdf(self):
        return b"%PDF-1.4 fake-etiqueta"


class FakeWeasyPrintModule:
    HTML = FakeWeasyHTML


PDF_MODULE = FakeWeasyPrintModule()


def crear_usuario(rol):
    return CustomUser.objects.create_user(
        username=f"qr_{rol}_{CustomUser.objects.count()}",
        password="testpass123",
        rol=rol,
    )


def crear_activo(serial, **kwargs):
    defaults = {
        "tipo_dispositivo": "escritorio",
        "marca": "HP",
        "modelo": "EliteDesk",
        "estado": "disponible",
    }
    defaults.update(kwargs)
    return Activo.objects.create(serial=serial, **defaults)


class EtiquetasQRBase(TestCase):
    def setUp(self):
        self.usuario = crear_usuario("superadmin")
        self.activo = crear_activo("SN-TEST-001", nombre_equipo="PC-01")
        self.client.force_login(self.usuario)

    def _enter_pdf(self):
        return patch.dict("sys.modules", {"weasyprint": PDF_MODULE})


class QrImagenTests(EtiquetasQRBase):
    def test_no_autenticado_redirige_a_login(self):
        self.client.logout()
        response = self.client.get(reverse("inventario:qr_imagen", args=[self.activo.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_devuelve_png_del_activo(self):
        response = self.client.get(reverse("inventario:qr_imagen", args=[self.activo.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))
        self.assertEqual(response["Cache-Control"], "public, max-age=86400")


class QrEtiquetaPdfTests(EtiquetasQRBase):
    def test_no_autenticado_redirige_a_login(self):
        self.client.logout()
        response = self.client.get(reverse("inventario:etiqueta", args=[self.activo.pk]))
        self.assertEqual(response.status_code, 302)

    def test_tecnico_puede_generar_etiqueta(self):
        tecnico = crear_usuario("tecnico")
        self.client.force_login(tecnico)
        with self._enter_pdf():
            response = self.client.get(reverse("inventario:etiqueta", args=[self.activo.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response.content, b"%PDF-1.4 fake-etiqueta")
        self.assertIn("etiqueta_SN-TEST-001.pdf", response["Content-Disposition"])

    def test_etiqueta_inexistente_404(self):
        with self._enter_pdf():
            response = self.client.get(reverse("inventario:etiqueta", args=[99999]))
        self.assertEqual(response.status_code, 404)


class QrEtiquetasMasivasTests(EtiquetasQRBase):
    def setUp(self):
        super().setUp()
        self.activo2 = crear_activo("SN-TEST-002", tipo_dispositivo="monitor")

    def test_no_autenticado_redirige_a_login(self):
        self.client.logout()
        response = self.client.get(reverse("inventario:etiquetas"))
        self.assertEqual(response.status_code, 302)

    def test_get_muestra_lista_de_activos(self):
        response = self.client.get(reverse("inventario:etiquetas"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SN-TEST-001")
        self.assertContains(response, "SN-TEST-002")

    def test_post_genera_pdf_de_seleccion(self):
        with self._enter_pdf():
            response = self.client.post(
                reverse("inventario:etiquetas"),
                {"activos": [self.activo.pk, self.activo2.pk]},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("etiquetas_qr.pdf", response["Content-Disposition"])

    def test_post_sin_seleccion_redirige_con_error(self):
        response = self.client.post(reverse("inventario:etiquetas"), {"activos": []})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("inventario:etiquetas"), response.url)


class EtiquetaTemplateTests(EtiquetasQRBase):
    def test_etiqueta_context_genera_qr_y_la_plantilla_renderiza(self):
        request = RequestFactory().get("/")
        label = _etiqueta_context(request, self.activo)
        self.assertTrue(label["qr"].startswith("data:image/png;base64,"))
        self.assertEqual(label["serial"], "SN-TEST-001")
        self.assertEqual(label["config"].nombre_empresa, "REDIHOS S.A.S")

        html = render_to_string("inventario/etiqueta_pdf.html", {"labels": [label]})
        self.assertIn("SN-TEST-001", html)
        self.assertIn("data:image/png;base64,", html)
        self.assertIn("REDIHOS S.A.S", html)