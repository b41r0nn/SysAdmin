"""Hoja de vida y reportes con el formato nuevo: resumen del checklist, fallas, estado final y actas."""

import sys
from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from mantenimiento.ayudas_pruebas import crear_pc, crear_usuario
from mantenimiento.ejecucion import cerrar_orden, iniciar_preventivo, marcar_punto
from mantenimiento.models import OrdenMantenimiento
from mantenimiento.services import hoja_de_vida_pdf_bytes

HOY = date(2026, 10, 23)


class FakeWeasy:
    """Reemplaza ``weasyprint`` (no carga en Windows) y guarda el HTML recibido."""

    html = ""

    class HTML:
        def __init__(self, string="", **kw):
            FakeWeasy.html = string

        def write_pdf(self):
            return b"%PDF-1.4 fake"


def _con_weasy():
    return patch.dict(sys.modules, {"weasyprint": FakeWeasy})


def _cerrar(activo, tecnico, fallas=None, estado_final="operativo_obs", observaciones="Revisar pronto"):
    with patch("mantenimiento.ejecucion.snapshot_software_ocs", return_value=[]):
        orden = iniciar_preventivo(activo, tecnico, HOY)
    fallas = fallas or {}
    for item in orden.checklist_items.all():
        if item.descripcion in fallas:
            marcar_punto(item, "falla", fallas[item.descripcion])
        else:
            marcar_punto(item, "bien")
    cerrar_orden(orden, tecnico, fecha_cierre=HOY, estado_final=estado_final, observaciones=observaciones, hoy=HOY)
    orden.refresh_from_db()
    return orden


class HojaDeVidaV2Tests(TestCase):
    def setUp(self):
        self.tecnico = crear_usuario("tecnico", first_name="Ana", last_name="Técnica")
        self.client.force_login(self.tecnico)
        self.pc = crear_pc(serial="SN-HV-1")
        self.orden = _cerrar(self.pc, self.tecnico, fallas={"Bisagras": "Floja"})

    def test_hoja_de_vida_muestra_resumen_fallas_y_acta(self):
        resp = self.client.get(reverse("mantenimiento:hoja_de_vida", args=[self.pc.pk]))
        self.assertContains(resp, "11 bien")
        self.assertContains(resp, "1 con falla")
        self.assertContains(resp, "Bisagras (falla): Floja")
        self.assertNotContains(resp, "Revisar pronto")
        self.assertContains(resp, reverse("mantenimiento:acta_pdf", args=[self.orden.pk]))
        self.assertContains(resp, "Operativo con observaciones")

    def test_enlace_acta_firmada_solo_si_existe(self):
        resp = self.client.get(reverse("mantenimiento:hoja_de_vida", args=[self.pc.pk]))
        self.assertNotContains(resp, "Acta firmada")
        OrdenMantenimiento.objects.filter(pk=self.orden.pk).update(acta_firmada="mantenimiento/actas/a.pdf")
        resp = self.client.get(reverse("mantenimiento:hoja_de_vida", args=[self.pc.pk]))
        self.assertContains(resp, "Acta firmada")
        self.assertContains(resp, "mantenimiento/actas/a.pdf")

    def test_orden_abierta_o_formato_anterior_sin_enlace_de_acta(self):
        otro = crear_pc(serial="SN-HV-2")
        vieja = OrdenMantenimiento.objects.create(
            activo=otro, tipo="correctivo", estado="cerrada", formato=1, fecha_cierre=HOY
        )
        resp = self.client.get(reverse("mantenimiento:hoja_de_vida", args=[otro.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, reverse("mantenimiento:acta_pdf", args=[vieja.pk]))
        self.assertNotContains(resp, "con falla")

    def test_hoja_de_vida_pdf_incluye_checklist(self):
        with _con_weasy():
            hoja_de_vida_pdf_bytes(self.pc)
        html = FakeWeasy.html
        self.assertIn("11 bien", html)
        self.assertIn("1 con falla", html)
        self.assertIn("Bisagras (falla): Floja", html)
        self.assertIn("Operativo con observaciones", html)
        self.assertIn("En garantía", html)
        self.assertIn("Estado final", html)

    def test_reporte_mantenimientos_pdf_columnas(self):
        with _con_weasy():
            resp = self.client.get(reverse("mantenimiento:reporte_mantenimientos_pdf"))
        self.assertEqual(resp.status_code, 200)
        html = FakeWeasy.html
        self.assertIn("<th>En garantía</th>", html)
        self.assertIn("<th>Estado final</th>", html)
        self.assertIn("Operativo con observaciones", html)
