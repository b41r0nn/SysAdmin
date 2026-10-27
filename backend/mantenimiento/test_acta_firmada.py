"""Subida del acta firmada escaneada de un mantenimiento cerrado."""

import tempfile
from datetime import date
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from mantenimiento.ayudas_pruebas import crear_pc, crear_usuario
from mantenimiento.models import OrdenMantenimiento


def _orden(estado="cerrada", formato=2, serial="SN-AF-1", **kw):
    return OrdenMantenimiento.objects.create(
        activo=crear_pc(serial=serial),
        tipo="preventivo",
        estado=estado,
        formato=formato,
        fecha_cierre=date(2026, 10, 23) if estado == "cerrada" else None,
        **kw,
    )


def _pdf(nombre="acta.pdf", contenido=b"%PDF-1.4 firmada"):
    return SimpleUploadedFile(nombre, contenido, content_type="application/pdf")


class SubirActaFirmadaTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.media = override_settings(MEDIA_ROOT=self.tmp.name)
        self.media.enable()
        self.addCleanup(self.media.disable)
        self.tecnico = crear_usuario("tecnico")
        self.client.force_login(self.tecnico)

    def _subir(self, orden, archivo):
        return self.client.post(
            reverse("mantenimiento:subir_acta_firmada", args=[orden.pk]), {"archivo": archivo}
        )

    def test_subir_pdf_guarda_y_quita_desactualizada(self):
        orden = _orden(acta_firmada_desactualizada=True)
        r = self._subir(orden, _pdf())
        self.assertRedirects(r, reverse("mantenimiento:detalle_orden", args=[orden.pk]))
        orden.refresh_from_db()
        self.assertTrue(orden.acta_firmada.name.startswith("mantenimiento/actas/"))
        self.assertFalse(orden.acta_firmada_desactualizada)

    def test_rechaza_extension(self):
        orden = _orden()
        r = self._subir(orden, SimpleUploadedFile("acta.exe", b"x"))
        self.assertContains(r, "Sube un PDF, JPG o PNG.")
        orden.refresh_from_db()
        self.assertFalse(orden.acta_firmada)

    def test_rechaza_mayor_a_10mb(self):
        orden = _orden()
        with patch("mantenimiento.forms.LIMITE_ACTA_BYTES", 10):
            r = self._subir(orden, _pdf(contenido=b"x" * 11))
        self.assertContains(r, "El archivo pasa de 10 MB.")
        orden.refresh_from_db()
        self.assertFalse(orden.acta_firmada)

    def test_solo_ordenes_cerradas(self):
        for orden in (_orden("abierta", serial="SN-AF-2"), _orden("cerrada", formato=1, serial="SN-AF-3")):
            url = reverse("mantenimiento:subir_acta_firmada", args=[orden.pk])
            self.assertEqual(self.client.get(url).status_code, 302)
            self._subir(orden, _pdf())
            orden.refresh_from_db()
            self.assertFalse(orden.acta_firmada)

    def test_archivo_se_sirve_con_permiso_de_mantenimiento(self):
        orden = _orden()
        self._subir(orden, _pdf())
        orden.refresh_from_db()
        r = self.client.get(f"/media/{orden.acta_firmada.name}")
        self.assertEqual(r.status_code, 200)
        # El archivo queda abierto hasta cerrar la respuesta (Windows no deja borrar
        # el tmpdir con el handle abierto), pero se cierra CONSUMIENDO el streaming:
        # el wrapper del test client lo cierra con close_old_connections desconectado.
        # Un r.close() directo dispara request_finished y, en PostgreSQL, cierra la
        # conexión de BD dentro del atomic del TestCase (ver core.tests._cerrar_archivo).
        self.assertEqual(b"".join(r.streaming_content), b"%PDF-1.4 firmada")
