"""Robustez del mantenimiento: carreras, transacciones largas, archivos y búsquedas.

Son los pendientes que quedaron anotados como menores en las revisiones de las
tareas 4, 6, 8, 11 y 12.
"""

import threading
from datetime import date
from unittest import skipUnless
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from mantenimiento import ejecucion
from mantenimiento.ayudas_pruebas import PORTATIL, crear_pc, crear_usuario
from mantenimiento.forms import SubirActaFirmadaForm
from mantenimiento.models import OrdenMantenimiento, PlantillaChecklist, ProgramacionMantenimiento, PuntoPlantilla


def _plantilla_portatil():
    """La plantilla de portátil, creándola si el flush de un TransactionTestCase la borró."""
    plantilla, nueva = PlantillaChecklist.objects.get_or_create(
        tipo_dispositivo="portatil", defaults={"frecuencia_meses": 12}
    )
    if nueva:
        PuntoPlantilla.objects.bulk_create(
            PuntoPlantilla(
                plantilla=plantilla, seccion=s, descripcion=d, posicion=i, aplica_en_garantia=g, activo=True
            )
            for i, (s, d, g) in enumerate(PORTATIL, start=1)
        )
    return plantilla


@skipUnless(connection.vendor == "postgresql", "select_for_update solo bloquea en PostgreSQL")
class IniciarPreventivoConcurrenteTests(TransactionTestCase):
    """Dos clics simultáneos en Iniciar no pueden abrir dos preventivos del mismo equipo."""

    def test_dos_inicios_simultaneos_crean_una_sola_orden(self):
        _plantilla_portatil()
        activo = crear_pc(serial="SN-CARRERA-1")
        usuario = crear_usuario("tecnico")
        barrera = threading.Barrier(2)
        inesperados = []

        def iniciar():
            try:
                barrera.wait()
                ejecucion.iniciar_preventivo(activo, usuario)
            except ValidationError:
                pass  # el segundo en llegar debe recibir exactamente esto
            except Exception as exc:  # noqa: BLE001 - lo reportamos como fallo del test
                inesperados.append(repr(exc))
            finally:
                connection.close()

        hilos = [threading.Thread(target=iniciar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(inesperados, [])
        self.assertEqual(OrdenMantenimiento.objects.filter(activo=activo, tipo="preventivo").count(), 1)


class IniciarPreventivoSinTransaccionLargaTests(TestCase):
    """La consulta a OCS no puede correr con la transacción abierta.

    Con OCS caído tarda hasta ~45 s; dentro del ``atomic`` eso deja la
    transacción (y los bloqueos del activo) tomada todo ese tiempo.
    """

    def test_el_snapshot_de_ocs_corre_fuera_del_atomic(self):
        _plantilla_portatil()
        activo = crear_pc(serial="SN-OCS-1")
        usuario = crear_usuario("tecnico")
        # El TestCase ya envuelve el test en atomics; lo que se compara es el
        # nivel de anidamiento: dentro del atomic del servicio habría uno más.
        nivel_fuera = len(connection.savepoint_ids)
        niveles = []

        def falso_snapshot(_activo):
            niveles.append(len(connection.savepoint_ids))
            return [{"name": "LibreOffice"}]

        with patch("mantenimiento.ejecucion.snapshot_software_ocs", falso_snapshot):
            orden = ejecucion.iniciar_preventivo(activo, usuario)

        self.assertEqual(niveles, [nivel_fuera])
        self.assertEqual(orden.software_snapshot, ["LibreOffice"])

    def test_no_llama_a_ocs_si_ya_hay_un_preventivo_abierto(self):
        _plantilla_portatil()
        activo = crear_pc(serial="SN-OCS-2")
        usuario = crear_usuario("tecnico")
        with patch("mantenimiento.ejecucion.snapshot_software_ocs", return_value=[]) as ocs:
            ejecucion.iniciar_preventivo(activo, usuario)
            self.assertEqual(ocs.call_count, 1)
            with self.assertRaises(ValidationError):
                ejecucion.iniciar_preventivo(activo, usuario)
            self.assertEqual(ocs.call_count, 1)


class ActaFirmadaContenidoTests(TestCase):
    """El acta firmada se valida por contenido, no solo por el nombre del archivo."""

    def _form(self, nombre, contenido):
        archivo = SimpleUploadedFile(nombre, contenido, content_type="application/pdf")
        return SubirActaFirmadaForm(data={}, files={"archivo": archivo})

    def test_rechaza_un_pdf_que_no_es_pdf(self):
        form = self._form("acta.pdf", b"esto no es un PDF, es un ejecutable renombrado")
        self.assertFalse(form.is_valid())
        self.assertIn("El archivo no es un PDF, JPG o PNG de verdad.", form.errors["archivo"])

    def test_acepta_pdf_jpg_y_png_de_verdad(self):
        for nombre, contenido in (
            ("acta.pdf", b"%PDF-1.4 firmada"),
            ("acta.jpg", b"\xff\xd8\xff\xe0 scan"),
            ("acta.png", b"\x89PNG\r\n\x1a\n scan"),
        ):
            with self.subTest(nombre=nombre):
                self.assertTrue(self._form(nombre, contenido).is_valid())


class ReabrirConOtroPreventivoAbiertoTests(TestCase):
    """Reabrir no puede dejar dos preventivos abiertos del mismo equipo."""

    def test_no_se_reabre_si_el_equipo_ya_tiene_otro_preventivo_abierto(self):
        activo = crear_pc(serial="SN-REABRIR-1")
        cerrada = OrdenMantenimiento.objects.create(
            activo=activo, tipo="preventivo", estado="cerrada", formato=2, fecha_cierre=date(2026, 10, 20)
        )
        OrdenMantenimiento.objects.create(activo=activo, tipo="preventivo", estado="en_proceso", formato=2)

        with self.assertRaises(ValidationError) as caso:
            ejecucion.reabrir_orden(cerrada)
        self.assertIn("ya tiene un mantenimiento preventivo abierto", str(caso.exception))
        cerrada.refresh_from_db()
        self.assertEqual(cerrada.estado, "cerrada")

    def test_se_reabre_si_no_hay_otro_abierto(self):
        activo = crear_pc(serial="SN-REABRIR-2")
        cerrada = OrdenMantenimiento.objects.create(
            activo=activo, tipo="preventivo", estado="cerrada", formato=2, fecha_cierre=date(2026, 10, 20)
        )
        ejecucion.reabrir_orden(cerrada)
        cerrada.refresh_from_db()
        self.assertEqual(cerrada.estado, "en_proceso")
        self.assertIsNone(cerrada.fecha_cierre)


class CalendarioSinEquiposDeBajaTests(TestCase):
    """El calendario no muestra la programación de equipos dados de baja (el tablero ya los excluye)."""

    def test_no_salen_las_programaciones_de_equipos_dados_de_baja(self):
        de_baja = crear_pc(serial="SN-BAJA-1", estado="dado_de_baja")
        en_uso = crear_pc(serial="SN-USO-1")
        for activo in (de_baja, en_uso):
            ProgramacionMantenimiento.objects.update_or_create(
                activo=activo, defaults={"fecha_programada": date(2026, 11, 10)}
            )
        cliente = Client()
        cliente.force_login(crear_usuario("tecnico"))

        eventos = cliente.get(reverse("mantenimiento:calendario_eventos")).json()
        titulos = [e["title"] for e in eventos]

        self.assertIn("Programado · SN-USO-1", titulos)
        self.assertNotIn("Programado · SN-BAJA-1", titulos)


class BusquedaPorNombreCompletoTests(TestCase):
    """Buscar "Nombre Apellido" en el historial encuentra las órdenes de ese técnico."""

    def test_busca_por_nombre_y_apellido_juntos(self):
        tecnico = crear_usuario("tecnico", first_name="Carlos", last_name="Ramírez")
        activo = crear_pc(serial="SN-BUSCA-1")
        orden = OrdenMantenimiento.objects.create(
            activo=activo, tipo="preventivo", estado="cerrada", formato=2,
            fecha_cierre=date(2026, 10, 20), tecnico=tecnico,
        )
        cliente = Client()
        cliente.force_login(crear_usuario("admin"))

        url = reverse("mantenimiento:lista_ordenes")
        for busqueda in ("Carlos Ramírez", "carlos ramírez", "Ramírez", "Carlos"):
            with self.subTest(busqueda=busqueda):
                html = cliente.get(url, {"q": busqueda}).content.decode()
                self.assertTrue(activo.serial in html, f"no encontró la orden #{orden.pk} buscando «{busqueda}»")
