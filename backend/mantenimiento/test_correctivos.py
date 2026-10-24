from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from mantenimiento.ayudas_pruebas import crear_pc, crear_usuario
from mantenimiento.ejecucion import errores_para_cerrar, iniciar_preventivo, marcar_punto
from mantenimiento.forms import CerrarOrdenForm, OrdenForm
from mantenimiento.models import ChecklistItem, OrdenMantenimiento

HOY = date(2026, 10, 23)


def _con_crlf(n):
    """Texto de ``n`` caracteres como los cuenta el navegador, enviado con CRLF."""
    base = ("a\n" + "a" * 8) * (n // 10) + "a" * (n % 10)
    assert len(base) == n
    return base.replace("\n", "\r\n")


class CorrectivosBase(TestCase):
    def setUp(self):
        self.user = crear_usuario(rol="superadmin")
        self.client.force_login(self.user)
        self.pc = crear_pc()

    def _datos(self, **extra):
        return {
            "activo": self.pc.pk,
            "prioridad": "alta",
            "fecha_apertura": HOY.isoformat(),
            "descripcion": "No enciende",
            **extra,
        }

    def _correctivo(self, **kw):
        datos = {"activo": self.pc, "tipo": "correctivo", "fecha_apertura": HOY, **kw}
        return OrdenMantenimiento.objects.create(**datos)


class CrearCorrectivoTests(CorrectivosBase):
    def test_crear_correctivo_formato_actual_sin_checklist(self):
        resp = self.client.post(
            reverse("mantenimiento:crear_orden"),
            self._datos(tipo="preventivo", estado="en_proceso", formato=1, plan=""),
        )
        self.assertEqual(resp.status_code, 302)
        orden = OrdenMantenimiento.objects.get(activo=self.pc)
        self.assertEqual(orden.tipo, "correctivo")
        self.assertEqual(orden.estado, "abierta")
        self.assertEqual(orden.formato, 2)
        self.assertIsNone(orden.plan)
        self.assertEqual(orden.checklist_items.count(), 0)
        self.assertEqual(orden.tecnico_asignado, "")

    def test_formulario_no_tiene_campos_viejos(self):
        form = OrdenForm()
        for nombre in form.fields:
            self.assertFalse(nombre.startswith(("accion_", "parte_")), nombre)
        for prohibido in ("plan", "tipo", "estado", "fecha_cierre", "tecnico_asignado"):
            self.assertNotIn(prohibido, form.fields)
        self.assertEqual(form.fields["acciones"].label, "Solución / acciones realizadas")
        resp = self.client.get(reverse("mantenimiento:crear_orden"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Plan asociado")
        self.assertNotContains(resp, "Estado general de partes")

    def test_crear_con_estado_cerrada_no_cierra(self):
        self.client.post(
            reverse("mantenimiento:crear_orden"),
            self._datos(estado="cerrada", fecha_cierre=HOY.isoformat()),
        )
        orden = OrdenMantenimiento.objects.get(activo=self.pc)
        self.assertEqual(orden.estado, "abierta")
        self.assertIsNone(orden.fecha_cierre)

    def test_crear_guarda_software_del_textarea(self):
        self.client.post(
            reverse("mantenimiento:crear_orden"),
            self._datos(software_snapshot_text="Chrome\nAcrobat"),
        )
        self.assertEqual(OrdenMantenimiento.objects.get().software_snapshot, ["Chrome", "Acrobat"])


class EditarCorrectivoTests(CorrectivosBase):
    def test_editar_correctivo_cambia_datos(self):
        orden = self._correctivo()
        otro = crear_pc(serial="SN-OTRO")
        resp = self.client.post(
            reverse("mantenimiento:editar_orden", args=[orden.pk]),
            self._datos(activo=otro.pk, diagnostico="Fuente dañada", acciones="Se cambió"),
        )
        self.assertEqual(resp.status_code, 302)
        orden.refresh_from_db()
        self.assertEqual(orden.activo, otro)
        self.assertEqual(orden.diagnostico, "Fuente dañada")

    def test_editar_con_estado_cerrada_no_cierra(self):
        orden = self._correctivo()
        self.client.post(
            reverse("mantenimiento:editar_orden", args=[orden.pk]),
            self._datos(estado="cerrada", fecha_cierre=HOY.isoformat()),
        )
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "abierta")
        self.assertIsNone(orden.fecha_cierre)

    def test_editar_preventivo_no_cambia_el_equipo(self):
        orden = iniciar_preventivo(self.pc, self.user, HOY)
        otro = crear_pc(serial="SN-OTRO")
        form = OrdenForm(instance=orden)
        for nombre in ("activo", "descripcion", "diagnostico", "acciones"):
            self.assertNotIn(nombre, form.fields)
        resp = self.client.post(
            reverse("mantenimiento:editar_orden", args=[orden.pk]),
            {
                "activo": otro.pk,
                "prioridad": "baja",
                "fecha_apertura": HOY.isoformat(),
                "diagnostico": "x",
                "descripcion": "y",
            },
        )
        self.assertEqual(resp.status_code, 302)
        orden.refresh_from_db()
        self.assertEqual(orden.activo, self.pc)
        self.assertEqual(orden.prioridad, "baja")
        self.assertEqual(orden.diagnostico, "")


class LimitesTextoTests(CorrectivosBase):
    def _form(self, **extra):
        return OrdenForm(self._datos(**extra))

    def test_diagnostico_maximo_600(self):
        self.assertTrue(self._form(diagnostico="a" * 600).is_valid())
        form = self._form(diagnostico="a" * 601)
        self.assertFalse(form.is_valid())
        self.assertIn("diagnostico", form.errors)
        form = self._form(acciones="a" * 601)
        self.assertIn("acciones", form.errors)

    def test_crlf_cuenta_como_un_caracter(self):
        form = self._form(diagnostico=_con_crlf(600), acciones=_con_crlf(600))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(len(form.cleaned_data["diagnostico"]), 600)
        form = self._form(diagnostico=_con_crlf(601))
        self.assertIn("diagnostico", form.errors)

    def _cerrar_form(self, orden, **extra):
        datos = {"fecha_cierre": HOY.isoformat(), "estado_final": "operativo", **extra}
        return CerrarOrdenForm(datos, orden=orden, pedir_datos_tecnico=False)

    def test_cerrar_form_crlf(self):
        orden = self._correctivo()
        form = self._cerrar_form(
            orden, observaciones=_con_crlf(600), diagnostico=_con_crlf(600), acciones=_con_crlf(600)
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("\r", form.cleaned_data["observaciones"])
        for campo in ("observaciones", "diagnostico", "acciones"):
            form = self._cerrar_form(
                orden, **{"diagnostico": "d", "acciones": "a", "observaciones": "", campo: _con_crlf(601)}
            )
            self.assertIn(campo, form.errors)

    def test_errores_para_cerrar_normaliza_crlf(self):
        orden = self._correctivo()
        errores = errores_para_cerrar(
            orden,
            fecha_cierre=HOY,
            estado_final="operativo",
            hoy=HOY,
            observaciones=_con_crlf(600),
            diagnostico=_con_crlf(600),
            acciones=_con_crlf(600),
        )
        self.assertEqual(errores, [])

    def test_observacion_de_punto_crlf(self):
        orden = iniciar_preventivo(self.pc, self.user, HOY)
        item = orden.checklist_items.first()
        marcar_punto(item, "falla", _con_crlf(150))
        item.refresh_from_db()
        self.assertEqual(len(item.observacion), 150)
        with self.assertRaises(ValidationError):
            marcar_punto(item, "falla", _con_crlf(151))


class CanceladaTests(CorrectivosBase):
    def test_cancelada_no_se_puede_cerrar(self):
        orden = self._correctivo(estado="cancelada")
        errores = errores_para_cerrar(
            orden,
            fecha_cierre=HOY,
            estado_final="operativo",
            observaciones="",
            diagnostico="d",
            acciones="a",
            hoy=HOY,
        )
        self.assertEqual(errores, ["Un mantenimiento cancelado no se puede cerrar."])

    def test_detalle_de_cancelada_sin_boton_cerrar(self):
        orden = self._correctivo(estado="cancelada")
        resp = self.client.get(reverse("mantenimiento:detalle_orden", args=[orden.pk]))
        self.assertNotContains(resp, reverse("mantenimiento:cerrar_orden", args=[orden.pk]))
        abierta = self._correctivo()
        resp = self.client.get(reverse("mantenimiento:detalle_orden", args=[abierta.pk]))
        self.assertContains(resp, reverse("mantenimiento:cerrar_orden", args=[abierta.pk]))


class DetalleTests(CorrectivosBase):
    def test_detalle_correctivo_formato_actual(self):
        orden = self._correctivo(diagnostico="Fuente dañada", acciones="Se cambió la fuente")
        resp = self.client.get(reverse("mantenimiento:detalle_orden", args=[orden.pk]))
        self.assertContains(resp, "Diagnóstico")
        self.assertContains(resp, "Solución / acciones realizadas")
        self.assertContains(resp, "Fuente dañada")
        self.assertNotContains(resp, "Estado general de partes")

    def test_orden_vieja_muestra_estado_de_partes(self):
        pc = crear_pc(serial="SN-VIEJO", tipo="portatil")
        orden = OrdenMantenimiento.objects.create(
            activo=pc,
            tipo="correctivo",
            formato=1,
            estado="cerrada",
            fecha_apertura=HOY,
            estado_partes={"pantalla": "mal"},
            accion_limpieza_general=True,
        )
        resp = self.client.get(reverse("mantenimiento:detalle_orden", args=[orden.pk]))
        self.assertContains(resp, "Pantalla")
        self.assertContains(resp, "Mal estado")
        self.assertContains(resp, "Limpieza general")

    def test_orden_vieja_muestra_checklist_solo_lectura(self):
        orden = OrdenMantenimiento.objects.create(
            activo=self.pc, tipo="preventivo", formato=1, estado="cerrada", fecha_apertura=HOY
        )
        ChecklistItem.objects.create(orden=orden, descripcion="Revisión visual vieja", completado=True)
        resp = self.client.get(reverse("mantenimiento:detalle_orden", args=[orden.pk]))
        self.assertContains(resp, "Revisión visual vieja")
        self.assertNotContains(resp, "Agregar item al checklist")
