from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from mantenimiento.ayudas_pruebas import asignar, crear_pc, crear_usuario
from mantenimiento.models import OrdenMantenimiento, ProgramacionMantenimiento


def _hoy():
    return timezone.localdate()


def _le_toca(serial="SN-TOCA"):
    # Garantía vencida hace dos años: le toca desde entonces.
    return crear_pc(serial, compra=_hoy() - timedelta(days=1100), meses=12)


def _en_garantia(serial="SN-GARANTIA"):
    return crear_pc(serial, compra=_hoy() - timedelta(days=30), meses=24)


class InicioTests(TestCase):
    def setUp(self):
        self.client.force_login(crear_usuario("tecnico"))
        self.url = reverse("mantenimiento:inicio")

    def test_por_hacer_muestra_los_que_les_toca_y_no_los_de_garantia(self):
        _le_toca()
        _en_garantia()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "SN-TOCA")
        self.assertNotContains(resp, "SN-GARANTIA")

    def test_pestana_en_garantia(self):
        _le_toca()
        _en_garantia()
        resp = self.client.get(self.url, {"tab": "en_garantia"})
        self.assertContains(resp, "SN-GARANTIA")
        self.assertContains(resp, "En garantía hasta")
        self.assertNotContains(resp, "SN-TOCA")

    def test_tarjetas_cuentan_por_estado(self):
        _le_toca("A")
        _le_toca("B")
        _en_garantia("C")
        programado = _le_toca("D")
        ProgramacionMantenimiento.objects.create(activo=programado, fecha_programada=_hoy() + timedelta(days=5))
        resp = self.client.get(self.url)
        self.assertEqual(
            resp.context["conteos"], {"programado": 1, "le_toca": 2, "en_garantia": 1, "al_dia": 0}
        )

    def test_sin_rojo_de_vencido(self):
        _le_toca()
        resp = self.client.get(self.url)
        self.assertContains(resp, "Le toca desde")
        self.assertContains(resp, "text-bg-warning")
        self.assertNotContains(resp, "bg-danger")
        self.assertNotContains(resp, "encid")

    def test_lectura_no_ve_programar_ni_iniciar(self):
        _le_toca()
        self.client.force_login(crear_usuario("lectura"))
        resp = self.client.get(self.url)
        self.assertContains(resp, "SN-TOCA")
        self.assertNotContains(resp, "Programar")
        self.assertNotContains(resp, "Iniciar")

    def test_escritura_ve_programar_e_iniciar(self):
        activo = _le_toca()
        resp = self.client.get(self.url)
        self.assertContains(resp, "Programar")
        self.assertContains(resp, "Iniciar")
        self.assertContains(resp, reverse("mantenimiento:iniciar_preventivo", args=[activo.pk]))

    def test_responsable_o_no_asignado(self):
        asignado = _le_toca("SN-CON")
        _le_toca("SN-SIN")
        asignar(asignado)
        resp = self.client.get(self.url)
        self.assertContains(resp, "Marta López Gómez")
        self.assertContains(resp, "Finanzas")
        self.assertContains(resp, "No asignado")

    def test_ultimo_mantenimiento_nunca_o_fecha(self):
        _le_toca()
        self.assertContains(self.client.get(self.url), "Nunca")

    def test_pestana_desconocida_cae_en_por_hacer(self):
        _le_toca()
        self.assertContains(self.client.get(self.url, {"tab": "xx"}), "SN-TOCA")

    def test_requiere_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_cuenta_fallas_reportadas(self):
        activo = _le_toca()
        OrdenMantenimiento.objects.create(activo=activo, tipo="correctivo", estado="reportada")
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["fallas"], 1)
        self.assertContains(resp, "Fallas reportadas (1)")


class ProgramarTests(TestCase):
    def setUp(self):
        self.client.force_login(crear_usuario("tecnico"))
        self.activo = _le_toca()
        self.url = reverse("mantenimiento:programar", args=[self.activo.pk])
        self.fecha = _hoy() + timedelta(days=10)

    def test_programar_y_quitar_fecha(self):
        resp = self.client.post(self.url, {"fecha_programada": self.fecha.isoformat(), "tab": "por_hacer"})
        self.assertRedirects(resp, reverse("mantenimiento:inicio") + "?tab=por_hacer")
        prog = ProgramacionMantenimiento.objects.get(activo=self.activo)
        self.assertEqual(prog.fecha_programada, self.fecha)
        self.client.post(self.url, {"fecha_programada": "", "tab": "por_hacer"})
        prog.refresh_from_db()
        self.assertIsNone(prog.fecha_programada)

    def test_programar_requiere_escritura(self):
        self.client.force_login(crear_usuario("lectura"))
        resp = self.client.post(self.url, {"fecha_programada": self.fecha.isoformat()})
        self.assertRedirects(resp, reverse("core:dashboard"), fetch_redirect_response=False)
        self.assertFalse(ProgramacionMantenimiento.objects.exists())

    def test_fecha_invalida_no_guarda(self):
        ProgramacionMantenimiento.objects.create(activo=self.activo, fecha_programada=self.fecha)
        resp = self.client.post(self.url, {"fecha_programada": "2026-13-40", "tab": "por_hacer"}, follow=True)
        self.assertContains(resp, "Fecha no válida")
        self.assertEqual(ProgramacionMantenimiento.objects.get().fecha_programada, self.fecha)

    def test_get_no_permitido(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_htmx_devuelve_la_tabla(self):
        resp = self.client.post(
            self.url, {"fecha_programada": self.fecha.isoformat(), "tab": "por_hacer"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "SN-TOCA")
        self.assertContains(resp, "Programado")
        self.assertNotContains(resp, "<html")

    def test_htmx_fecha_invalida_muestra_el_error(self):
        resp = self.client.post(
            self.url, {"fecha_programada": "2026-13-40", "tab": "por_hacer"}, HTTP_HX_REQUEST="true"
        )
        self.assertContains(resp, "Fecha no válida")
        self.assertFalse(ProgramacionMantenimiento.objects.exists())

    def test_quitar_sin_fila_no_crea(self):
        self.client.post(self.url, {"fecha_programada": ""})
        self.assertFalse(ProgramacionMantenimiento.objects.exists())


class HistorialTests(TestCase):
    def test_fallas_reportadas_filtra(self):
        self.client.force_login(crear_usuario("tecnico"))
        reportada = OrdenMantenimiento.objects.create(
            activo=crear_pc("SN-FALLA"), tipo="correctivo", estado="reportada"
        )
        OrdenMantenimiento.objects.create(
            activo=crear_pc("SN-CERRADA"), tipo="correctivo", estado="cerrada", fecha_cierre=_hoy()
        )
        OrdenMantenimiento.objects.create(activo=crear_pc("SN-PREV"), tipo="preventivo", estado="en_proceso")
        resp = self.client.get(reverse("mantenimiento:lista_ordenes"), {"fallas": "1"})
        self.assertEqual(list(resp.context["ordenes"]), [reportada])
        self.assertContains(resp, "SN-FALLA")
        self.assertNotContains(resp, "SN-CERRADA")

    def test_la_url_del_historial(self):
        self.assertEqual(reverse("mantenimiento:lista_ordenes"), "/mantenimiento/historial/")
        self.assertEqual(reverse("mantenimiento:inicio"), "/mantenimiento/")
