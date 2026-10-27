"""Retiro de los planes por categoría (Tarea 11).

Los planes, el estado de partes editable y el checklist viejo con casillas se
fueron; la programación por equipo los reemplaza en el calendario. Las órdenes
del formato anterior se siguen viendo en todas partes.
"""

from datetime import timedelta
from unittest.mock import patch

from django.apps import apps
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from mantenimiento.ayudas_pruebas import crear_pc, crear_usuario
from mantenimiento.models import (
    FORMATO_ANTERIOR,
    ChecklistItem,
    OrdenMantenimiento,
    ProgramacionMantenimiento,
)


class _FakeHTML:
    def __init__(self, *args, **kwargs):
        pass

    def write_pdf(self, *args, **kwargs):
        return b"%PDF-1.4 fake"


FAKE_WEASY = type("M", (), {"HTML": _FakeHTML})()


def _hoy():
    return timezone.localdate()


class RetiroPlanesTests(TestCase):
    def setUp(self):
        self.client.force_login(crear_usuario("superadmin"))

    def test_orden_formato_anterior_sigue_visible(self):
        pc = crear_pc("SN-VIEJA")
        orden = OrdenMantenimiento.objects.create(
            activo=pc,
            tipo="correctivo",
            formato=FORMATO_ANTERIOR,
            estado="cerrada",
            fecha_apertura=_hoy() - timedelta(days=10),
            fecha_cierre=_hoy() - timedelta(days=9),
            tecnico_asignado="Pedro Gómez",
            estado_partes={"pantalla": "mal", "teclado": "bien"},
            accion_limpieza_general=True,
        )
        paginas = [
            reverse("mantenimiento:detalle_orden", args=[orden.pk]),
            reverse("mantenimiento:hoja_de_vida", args=[pc.pk]),
            reverse("mantenimiento:hoja_de_vida_pdf", args=[pc.pk]),
            reverse("mantenimiento:lista_ordenes"),
            reverse("reports:mantenimiento_excel"),
        ]
        for url in paginas:
            with self.subTest(url=url), patch.dict("sys.modules", {"weasyprint": FAKE_WEASY}):
                self.assertEqual(self.client.get(url).status_code, 200)
        detalle = self.client.get(paginas[0])
        self.assertContains(detalle, "Pantalla")
        self.assertContains(detalle, "Mal estado")
        self.assertContains(self.client.get(paginas[3]), "Pedro Gómez")

    def test_orden_vieja_con_checklist_se_ve_sin_casillas(self):
        orden = OrdenMantenimiento.objects.create(
            activo=crear_pc(), tipo="preventivo", formato=FORMATO_ANTERIOR, estado="cerrada", fecha_apertura=_hoy()
        )
        ChecklistItem.objects.create(orden=orden, descripcion="Revisión visual vieja")
        resp = self.client.get(reverse("mantenimiento:detalle_orden", args=[orden.pk]))
        self.assertContains(resp, "Revisión visual vieja")
        self.assertContains(resp, "formato anterior")

    def test_ya_no_existen_rutas_de_planes(self):
        for nombre, args in [
            ("mantenimiento:lista_planes", []),
            ("mantenimiento:crear_plan", []),
            ("mantenimiento:detalle_plan", [1]),
            ("mantenimiento:toggle_checklist", [1]),
            ("mantenimiento:estado_partes_partial", []),
            ("mantenimiento:crear_item_checklist", [1]),
        ]:
            with self.subTest(ruta=nombre), self.assertRaises(NoReverseMatch):
                reverse(nombre, args=args)

    def test_ya_no_existen_planes_en_los_modelos(self):
        with self.assertRaises(LookupError):
            apps.get_model("mantenimiento", "PlanMantenimiento")
        campos_orden = {f.name for f in OrdenMantenimiento._meta.get_fields()}
        campos_punto = {f.name for f in ChecklistItem._meta.get_fields()}
        self.assertNotIn("plan", campos_orden)
        self.assertNotIn("plan", campos_punto)
        self.assertNotIn("completado", campos_punto)
        self.assertFalse(hasattr(OrdenMantenimiento, "checklist_items_completados"))

    def test_eventos_incluyen_ordenes_y_programados(self):
        pc = crear_pc("SN-CAL")
        orden = OrdenMantenimiento.objects.create(
            activo=pc, tipo="correctivo", estado="abierta", fecha_apertura=_hoy()
        )
        programado = crear_pc("SN-PROG")
        fecha = _hoy() + timedelta(days=5)
        ProgramacionMantenimiento.objects.create(activo=programado, fecha_programada=fecha)
        # Sin fecha no sale en el calendario.
        ProgramacionMantenimiento.objects.create(activo=crear_pc("SN-SIN-FECHA"), fecha_programada=None)

        resp = self.client.get(reverse("mantenimiento:calendario_eventos"))
        self.assertEqual(resp.status_code, 200)
        eventos = resp.json()
        titulos = [e["title"] for e in eventos]
        self.assertIn(f"Orden #{orden.id} · SN-CAL", titulos)
        self.assertIn(
            {
                "title": "Programado · SN-PROG",
                "start": fecha.isoformat(),
                "url": reverse("mantenimiento:hoja_de_vida", args=[programado.pk]),
                "color": "#0156a6",
            },
            eventos,
        )
        self.assertEqual(len(eventos), 2)
        self.assertFalse(any(t.startswith("Plan") for t in titulos))

    def test_calendario_sin_enlace_a_planes(self):
        resp = self.client.get(reverse("mantenimiento:calendario"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Planes")
        self.assertNotContains(resp, "planes")
        self.assertContains(resp, reverse("mantenimiento:inicio"))

    def test_historial_muestra_el_tecnico(self):
        pc = crear_pc("SN-TEC")
        tecnico = crear_usuario(first_name="Ana", last_name="Técnica")
        OrdenMantenimiento.objects.create(
            activo=pc, tipo="correctivo", estado="cerrada", fecha_apertura=_hoy(), tecnico=tecnico
        )
        OrdenMantenimiento.objects.create(
            activo=pc, tipo="correctivo", estado="cerrada", fecha_apertura=_hoy(), tecnico_asignado="Pedro Viejo"
        )
        resp = self.client.get(reverse("mantenimiento:lista_ordenes"))
        self.assertContains(resp, "Técnico")
        self.assertContains(resp, "Ana Técnica")
        self.assertContains(resp, "Pedro Viejo")
        self.assertNotContains(resp, ">Plan<")

    def test_historial_busca_por_el_tecnico_que_cerro(self):
        tecnico = crear_usuario(first_name="Ana", last_name="Técnica")
        OrdenMantenimiento.objects.create(
            activo=crear_pc("SN-HIST-1"), tipo="correctivo", estado="cerrada", fecha_apertura=_hoy(), tecnico=tecnico
        )
        OrdenMantenimiento.objects.create(
            activo=crear_pc("SN-HIST-2"), tipo="correctivo", estado="cerrada", fecha_apertura=_hoy()
        )
        for q in ("Ana", "Técnica"):
            with self.subTest(q=q):
                resp = self.client.get(reverse("mantenimiento:lista_ordenes"), {"q": q})
                self.assertContains(resp, "SN-HIST-1")
                self.assertNotContains(resp, "SN-HIST-2")


class NavegacionTests(TestCase):
    """Las pantallas que llevaban a la lista de órdenes o de planes vuelven a la pantalla principal."""

    def setUp(self):
        self.client.force_login(crear_usuario("superadmin"))
        self.inicio = reverse("mantenimiento:inicio")

    def test_nuevo_vuelve_a_la_pantalla_principal(self):
        resp = self.client.get(reverse("mantenimiento:nuevo"))
        self.assertContains(resp, f'<a href="{self.inicio}" class="text-decoration-none">Mantenimiento</a>', html=True)
        self.assertContains(resp, f'<a href="{self.inicio}" class="btn btn-outline-secondary">Cancelar</a>', html=True)
        self.assertNotContains(resp, ">Ordenes<")

    def test_correctivo_y_repuesto_vuelven_a_la_pantalla_principal(self):
        orden = OrdenMantenimiento.objects.create(
            activo=crear_pc(), tipo="correctivo", estado="abierta", fecha_apertura=_hoy()
        )
        for url in (
            reverse("mantenimiento:crear_orden"),
            reverse("mantenimiento:editar_orden", args=[orden.pk]),
            reverse("mantenimiento:crear_repuesto", args=[orden.pk]),
        ):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertContains(
                    resp, f'<a href="{self.inicio}" class="text-decoration-none">Mantenimiento</a>', html=True
                )
                self.assertNotContains(resp, ">Ordenes<")

    def test_hoja_de_vida_buscar_vuelve_a_la_pantalla_principal(self):
        resp = self.client.get(reverse("mantenimiento:hoja_de_vida_buscar"))
        self.assertContains(resp, self.inicio)
        self.assertNotContains(resp, "Planes")
