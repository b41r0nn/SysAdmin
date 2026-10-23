from datetime import date
from importlib import import_module

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from mantenimiento.ayudas_pruebas import (
    ESCRITORIO,
    PORTATIL,
    asignar,
    crear_pc,
    crear_usuario,
)
from mantenimiento.models import PlantillaChecklist, PuntoPlantilla, SECCIONES_SUGERIDAS


def _puntos(tipo):
    plantilla = PlantillaChecklist.objects.get(tipo_dispositivo=tipo)
    return [(p.seccion, p.descripcion, p.aplica_en_garantia) for p in plantilla.puntos.all()]


class PlantillasInicialesTests(TestCase):
    def test_portatil(self):
        self.assertEqual(_puntos("portatil"), PORTATIL)
        self.assertEqual(PlantillaChecklist.objects.get(tipo_dispositivo="portatil").frecuencia_meses, 12)

    def test_escritorio(self):
        self.assertEqual(_puntos("escritorio"), ESCRITORIO)

    def test_un_checklist_por_tipo(self):
        with self.assertRaises(IntegrityError):
            PlantillaChecklist.objects.create(tipo_dispositivo="portatil")

    def test_frecuencia_posicion_e_inicialmente_activos(self):
        for tipo, esperado in (("portatil", PORTATIL), ("escritorio", ESCRITORIO)):
            with self.subTest(tipo=tipo):
                plantilla = PlantillaChecklist.objects.get(tipo_dispositivo=tipo)
                puntos = list(plantilla.puntos.all())
                self.assertEqual(plantilla.frecuencia_meses, 12)
                # la posición es el índice dentro de la lista de su plantilla, desde 0
                self.assertEqual([p.posicion for p in puntos], list(range(len(esperado))))
                self.assertTrue(all(p.activo for p in puntos))


class MigracionDatosTests(TestCase):
    """La 0010 define su propia copia de la lista; aquí se prueban sus dos funciones."""

    def setUp(self):
        self.migracion = import_module("mantenimiento.migrations.0010_plantillas_iniciales")

    def test_reversa_borra_solo_las_dos_plantillas_iniciales(self):
        propia = PlantillaChecklist.objects.create(tipo_dispositivo="diadema")
        PuntoPlantilla.objects.create(plantilla=propia, seccion="Limpieza", descripcion="Limpieza externa")

        self.migracion.quitar_plantillas_iniciales(apps, None)

        self.assertEqual(
            list(PlantillaChecklist.objects.values_list("tipo_dispositivo", flat=True)), ["diadema"]
        )
        self.assertEqual(PuntoPlantilla.objects.count(), 1)

    def test_volver_a_aplicarla_no_duplica_ni_pisa(self):
        PuntoPlantilla.objects.create(
            plantilla=PlantillaChecklist.objects.get(tipo_dispositivo="escritorio"),
            seccion="Hardware",
            descripcion="Punto agregado a mano",
            posicion=99,
        )

        self.migracion.crear_plantillas_iniciales(apps, None)

        self.assertEqual(PlantillaChecklist.objects.filter(tipo_dispositivo="portatil").count(), 1)
        self.assertEqual(_puntos("portatil"), PORTATIL)
        self.assertEqual(_puntos("escritorio"), [*ESCRITORIO, ("Hardware", "Punto agregado a mano", False)])


class ModeloChecklistTests(TestCase):
    def test_nombre_legible_del_tipo(self):
        self.assertEqual(PlantillaChecklist(tipo_dispositivo="portatil").get_tipo_dispositivo_display(), "Portátil")
        # un tipo creado a mano (no está en inventario.TIPOS) se muestra tal cual
        self.assertEqual(PlantillaChecklist(tipo_dispositivo="Diadema").get_tipo_dispositivo_display(), "Diadema")

    def test_str_usa_el_nombre_legible(self):
        self.assertIn("Portátil", str(PlantillaChecklist(tipo_dispositivo="portatil")))

    def test_frecuencia_minima_un_mes(self):
        plantilla = PlantillaChecklist(tipo_dispositivo="diadema", frecuencia_meses=0)
        with self.assertRaises(ValidationError) as ctx:
            plantilla.full_clean()
        self.assertIn("frecuencia_meses", ctx.exception.message_dict)

    def test_punto_valores_por_defecto(self):
        plantilla = PlantillaChecklist.objects.create(tipo_dispositivo="diadema")
        punto = PuntoPlantilla.objects.create(plantilla=plantilla, seccion="Limpieza", descripcion="Limpieza externa")
        self.assertEqual((punto.posicion, punto.aplica_en_garantia, punto.activo), (0, False, True))
        self.assertEqual(plantilla.frecuencia_meses, 12)

    def test_puntos_ordenados_por_posicion_y_luego_por_id(self):
        plantilla = PlantillaChecklist.objects.create(tipo_dispositivo="diadema")
        for posicion, descripcion in ((2, "C"), (0, "A"), (1, "B1"), (1, "B2")):
            PuntoPlantilla.objects.create(
                plantilla=plantilla, seccion="Hardware", descripcion=descripcion, posicion=posicion
            )
        self.assertEqual([p.descripcion for p in plantilla.puntos.all()], ["A", "B1", "B2", "C"])

    def test_borrar_la_plantilla_borra_sus_puntos_y_solo_los_suyos(self):
        PlantillaChecklist.objects.get(tipo_dispositivo="portatil").delete()
        self.assertFalse(PuntoPlantilla.objects.filter(plantilla__tipo_dispositivo="portatil").exists())
        self.assertEqual(
            PuntoPlantilla.objects.filter(plantilla__tipo_dispositivo="escritorio").count(), len(ESCRITORIO)
        )

    def test_secciones_sugeridas(self):
        self.assertEqual(SECCIONES_SUGERIDAS, ["Hardware", "Limpieza", "Mantenimiento lógico"])
        self.assertEqual({seccion for seccion, _, _ in PORTATIL}, set(SECCIONES_SUGERIDAS))


class AdminChecklistTests(TestCase):
    def test_la_plantilla_se_edita_en_el_admin_con_sus_puntos_en_linea(self):
        self.client.force_login(crear_usuario("superadmin", is_staff=True, is_superuser=True))
        plantilla = PlantillaChecklist.objects.get(tipo_dispositivo="portatil")

        lista = self.client.get(reverse("admin:mantenimiento_plantillachecklist_changelist"))
        detalle = self.client.get(reverse("admin:mantenimiento_plantillachecklist_change", args=[plantilla.pk]))

        self.assertEqual(lista.status_code, 200)
        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, "Desarme del equipo")
        self.assertContains(detalle, "Actualizaciones de Windows")


class AyudasPruebasTests(TestCase):
    """Contrato de los ayudantes compartidos (los usan las demás pruebas del módulo)."""

    def test_crear_pc_valores_por_defecto(self):
        pc = crear_pc()
        self.assertEqual(
            (pc.serial, pc.tipo_dispositivo, pc.marca, pc.modelo, pc.estado),
            ("SN-PC-1", "portatil", "HP", "ProBook", "disponible"),
        )
        self.assertIsNone(pc.fecha_compra)
        self.assertIsNone(pc.garantia_fabrica_meses)

    def test_crear_pc_kw_sobrescribe_y_pasa_campos_del_activo(self):
        pc = crear_pc(
            "SN-PC-2",
            tipo="escritorio",
            compra=date(2025, 1, 15),
            meses=24,
            marca="Dell",
            estado="dado_de_baja",
            nombre_equipo="PT-12",
            ip_equipo="192.168.1.57",
        )
        self.assertEqual(
            (pc.serial, pc.tipo_dispositivo, pc.fecha_compra, pc.garantia_fabrica_meses),
            ("SN-PC-2", "escritorio", date(2025, 1, 15), 24),
        )
        self.assertEqual((pc.marca, pc.modelo, pc.estado), ("Dell", "ProBook", "dado_de_baja"))
        self.assertEqual((pc.nombre_equipo, pc.ip_equipo), ("PT-12", "192.168.1.57"))

    def test_asignar_crea_el_usuario_y_una_asignacion_activa(self):
        pc = crear_pc()
        asignacion = asignar(pc)
        self.assertEqual(asignacion.activo, pc)
        self.assertTrue(asignacion.activa)
        self.assertEqual(asignacion.fecha_asignacion, timezone.localdate())
        usuario = asignacion.usuario
        self.assertEqual(
            (usuario.nombre_completo, usuario.documento_identidad, usuario.cargo, usuario.area, usuario.correo),
            ("Marta López Gómez", "200300400", "Contadora", "Finanzas", "marta@example.com"),
        )

    def test_asignar_acepta_otro_responsable(self):
        asignacion = asignar(crear_pc(), nombre="Luis Mora", documento="1", cargo="Auxiliar", area="Compras")
        self.assertEqual(
            (asignacion.usuario.nombre_completo, asignacion.usuario.area), ("Luis Mora", "Compras")
        )

    def test_crear_usuario_con_rol_y_nombre_de_usuario_unico(self):
        tecnico = crear_usuario()
        admin = crear_usuario("admin", first_name="Ana", last_name="Técnica")
        self.assertNotEqual(tecnico.username, admin.username)
        self.assertEqual((tecnico.rol, admin.rol), ("tecnico", "admin"))
        self.assertEqual(admin.get_full_name(), "Ana Técnica")
        self.assertTrue(tecnico.check_password("x"))
