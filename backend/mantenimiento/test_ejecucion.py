from datetime import date
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from mantenimiento.ayudas_pruebas import PORTATIL, crear_pc, crear_usuario
from mantenimiento.ejecucion import iniciar_preventivo, marcar_punto
from mantenimiento.models import OrdenMantenimiento, PuntoPlantilla

HOY = date(2026, 10, 23)


def _sin_ocs():
    return patch("mantenimiento.ejecucion.snapshot_software_ocs", return_value=[{"name": "Office"}])


class IniciarPreventivoTests(TestCase):
    def setUp(self):
        p = _sin_ocs()
        p.start()
        self.addCleanup(p.stop)

    def test_fuera_de_garantia_copia_todos_los_puntos(self):
        orden = iniciar_preventivo(crear_pc(compra=date(2023, 1, 1), meses=12), crear_usuario(), HOY)
        self.assertEqual((orden.tipo, orden.estado, orden.en_garantia, orden.formato), ("preventivo", "en_proceso", False, 2))
        self.assertEqual([(i.seccion, i.descripcion, i.resultado) for i in orden.checklist_items.all()],
                         [(s, d, "") for s, d, _ in PORTATIL])
        self.assertEqual(orden.software_snapshot, ["Office"])

    def test_en_garantia_copia_solo_los_que_aplican(self):
        orden = iniciar_preventivo(crear_pc(compra=date(2026, 1, 1), meses=24), crear_usuario(), HOY)
        self.assertTrue(orden.en_garantia)
        self.assertEqual([i.descripcion for i in orden.checklist_items.all()],
                         ["Limpieza externa", "Actualizaciones de Windows", "Antivirus",
                          "Archivos temporales", "Estado del disco", "Programas de inicio"])

    def test_no_permite_dos_preventivos_abiertos(self):
        pc, u = crear_pc(), crear_usuario()
        iniciar_preventivo(pc, u, HOY)
        with self.assertRaisesMessage(ValidationError, "Este equipo ya tiene un mantenimiento preventivo abierto."):
            iniciar_preventivo(pc, u, HOY)

    def test_tipo_sin_checklist_no_inicia(self):
        with self.assertRaisesMessage(ValidationError, "No hay checklist para este tipo de equipo."):
            iniciar_preventivo(crear_pc(tipo="celular"), crear_usuario(), HOY)

    def test_equipo_dado_de_baja_no_inicia(self):
        with self.assertRaisesMessage(ValidationError, "El equipo está dado de baja."):
            iniciar_preventivo(crear_pc(estado="dado_de_baja"), crear_usuario(), HOY)

    def test_cambiar_la_plantilla_no_afecta_ordenes_iniciadas(self):
        orden = iniciar_preventivo(crear_pc(), crear_usuario(), HOY)
        PuntoPlantilla.objects.filter(descripcion="Pantalla").update(descripcion="Pantalla y marco")
        self.assertTrue(orden.checklist_items.filter(descripcion="Pantalla").exists())


class MarcarPuntoTests(TestCase):
    def setUp(self):
        p = _sin_ocs()
        p.start()
        self.addCleanup(p.stop)
        self.orden = iniciar_preventivo(crear_pc(), crear_usuario(), HOY)
        self.item = self.orden.checklist_items.get(descripcion="Bisagras")

    def test_falla_exige_observacion(self):
        with self.assertRaisesMessage(ValidationError, "Explica la falla en la observación."):
            marcar_punto(self.item, "falla", "  ")
        marcar_punto(self.item, "falla", "Bisagra izquierda floja")
        self.item.refresh_from_db()
        self.assertEqual((self.item.resultado, self.item.observacion), ("falla", "Bisagra izquierda floja"))

    def test_observacion_maximo_150(self):
        with self.assertRaisesMessage(ValidationError, "La observación no puede pasar de 150 caracteres."):
            marcar_punto(self.item, "bien", "x" * 151)

    def test_resultado_invalido(self):
        with self.assertRaisesMessage(ValidationError, "Resultado no válido."):
            marcar_punto(self.item, "otro")

    def test_no_se_marca_en_orden_cerrada(self):
        OrdenMantenimiento.objects.filter(pk=self.orden.pk).update(estado="cerrada")
        self.item.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "El mantenimiento ya está cerrado."):
            marcar_punto(self.item, "bien")


class VistasEjecucionTests(TestCase):
    def setUp(self):
        p = _sin_ocs()
        p.start()
        self.addCleanup(p.stop)
        self.tecnico = crear_usuario("tecnico")
        self.lectura = crear_usuario("lectura")
        self.pc = crear_pc()
        self.client.force_login(self.tecnico)

    def _iniciar(self, **datos):
        return self.client.post(reverse("mantenimiento:iniciar_preventivo", args=[self.pc.pk]), datos)

    def test_iniciar_redirige_al_detalle(self):
        resp = self._iniciar()
        orden = OrdenMantenimiento.objects.get()
        self.assertRedirects(resp, reverse("mantenimiento:detalle_orden", args=[orden.pk]))

    def test_iniciar_requiere_escritura(self):
        self.client.force_login(self.lectura)
        resp = self._iniciar()
        self.assertRedirects(resp, reverse("core:dashboard"), fetch_redirect_response=False)
        self.assertEqual(OrdenMantenimiento.objects.count(), 0)

    def test_iniciar_con_error_vuelve_a_volver_seguro(self):
        self._iniciar()
        resp = self._iniciar(volver="/mantenimiento/")
        self.assertRedirects(resp, "/mantenimiento/", fetch_redirect_response=False)
        mensajes = [str(m) for m in resp.wsgi_request._messages]
        self.assertIn("Este equipo ya tiene un mantenimiento preventivo abierto.", mensajes)

    def test_volver_externo_se_ignora(self):
        self._iniciar()
        resp = self._iniciar(volver="https://malo.example")
        self.assertRedirects(resp, reverse("mantenimiento:nuevo"), fetch_redirect_response=False)

    def test_marcar_punto_htmx_devuelve_la_tarjeta(self):
        self._iniciar()
        item = OrdenMantenimiento.objects.get().checklist_items.first()
        resp = self.client.post(reverse("mantenimiento:marcar_punto", args=[item.pk]),
                                {"resultado": "bien"}, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "1 de 12 marcados")

    def test_marcar_falla_sin_observacion_htmx_muestra_error(self):
        self._iniciar()
        item = OrdenMantenimiento.objects.get().checklist_items.first()
        resp = self.client.post(reverse("mantenimiento:marcar_punto", args=[item.pk]),
                                {"resultado": "falla", "observacion": ""}, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Explica la falla en la observación.")
        item.refresh_from_db()
        self.assertEqual(item.resultado, "")

    def test_detalle_muestra_la_tarjeta(self):
        self._iniciar()
        orden = OrdenMantenimiento.objects.get()
        resp = self.client.get(reverse("mantenimiento:detalle_orden", args=[orden.pk]))
        self.assertContains(resp, "0 de 12 marcados")

    def test_nuevo_preventivo_crea_y_redirige(self):
        resp = self.client.post(reverse("mantenimiento:nuevo"), {"activo": self.pc.pk, "tipo": "preventivo"})
        orden = OrdenMantenimiento.objects.get()
        self.assertRedirects(resp, reverse("mantenimiento:detalle_orden", args=[orden.pk]))

    def test_nuevo_correctivo_redirige_al_formulario(self):
        resp = self.client.post(reverse("mantenimiento:nuevo"), {"activo": self.pc.pk, "tipo": "correctivo"})
        self.assertRedirects(resp, f"{reverse('mantenimiento:crear_orden')}?activo={self.pc.pk}",
                             fetch_redirect_response=False)
