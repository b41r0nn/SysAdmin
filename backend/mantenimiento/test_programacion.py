from datetime import date, datetime, timezone as dt_timezone
from importlib import import_module

from django.apps import apps
from django.test import TestCase

from inventario.models import Activo
from mantenimiento.ayudas_pruebas import crear_pc
from mantenimiento.models import (
    FORMATO_ACTUAL,
    FORMATO_ANTERIOR,
    OrdenMantenimiento,
    PlantillaChecklist,
    ProgramacionMantenimiento,
)
from mantenimiento.programacion import (
    activos_programables,
    proximo_preventivo,
    situacion,
    tablero,
)

HOY = date(2026, 10, 23)


def _cerrada(activo, tipo, fecha_cierre, en_garantia=False):
    return OrdenMantenimiento.objects.create(
        activo=activo,
        tipo=tipo,
        estado="cerrada",
        fecha_apertura=fecha_cierre,
        fecha_cierre=fecha_cierre,
        en_garantia=en_garantia,
    )


class ReglaLeTocaTests(TestCase):
    def test_en_garantia_no_le_toca_hasta_que_vence(self):
        pc = crear_pc(compra=date(2025, 10, 1), meses=24)
        s = situacion(pc, HOY)
        self.assertEqual((s.estado, s.le_toca_desde), ("en_garantia", date(2027, 10, 1)))

    def test_le_toca_desde_el_vencimiento_si_nunca_tuvo_preventivo(self):
        s = situacion(crear_pc(compra=date(2023, 1, 10), meses=12), HOY)
        self.assertEqual((s.estado, s.le_toca_desde), ("le_toca", date(2024, 1, 10)))

    def test_despues_del_preventivo_completo_cuenta_desde_el_cierre(self):
        pc = crear_pc(compra=date(2023, 1, 10), meses=12)
        _cerrada(pc, "preventivo", date(2026, 3, 5), en_garantia=False)
        s = situacion(pc, HOY)
        self.assertEqual((s.estado, s.le_toca_desde), ("al_dia", date(2027, 3, 5)))

    def test_usa_la_frecuencia_de_la_plantilla(self):
        PlantillaChecklist.objects.filter(tipo_dispositivo="portatil").update(frecuencia_meses=6)
        pc = crear_pc(compra=date(2023, 1, 10), meses=12)
        _cerrada(pc, "preventivo", date(2026, 3, 5), en_garantia=False)
        self.assertEqual(situacion(pc, HOY).le_toca_desde, date(2026, 9, 5))

    def test_preventivo_en_garantia_y_correctivo_no_mueven_la_fecha(self):
        pc = crear_pc(compra=date(2025, 10, 1), meses=24)
        _cerrada(pc, "preventivo", date(2026, 5, 1), en_garantia=True)
        _cerrada(pc, "correctivo", date(2026, 6, 1))
        self.assertEqual(situacion(pc, HOY).le_toca_desde, date(2027, 10, 1))

    def test_sin_fecha_de_compra_le_toca_desde_su_registro(self):
        pc = crear_pc(compra=None)
        Activo.objects.filter(pk=pc.pk).update(fecha_creacion=datetime(2026, 1, 15, 12, tzinfo=dt_timezone.utc))
        pc.refresh_from_db()
        s = situacion(pc, HOY)
        self.assertEqual((s.estado, s.le_toca_desde), ("le_toca", date(2026, 1, 15)))

    def test_programado_gana_sobre_los_demas_estados(self):
        pc = crear_pc(compra=date(2025, 10, 1), meses=24)
        ProgramacionMantenimiento.objects.create(activo=pc, fecha_programada=date(2026, 11, 5))
        self.assertEqual(situacion(pc, HOY).estado, "programado")

    def test_ultimo_es_el_ultimo_cerrado_de_cualquier_tipo(self):
        pc = crear_pc(compra=date(2023, 1, 10), meses=12)
        _cerrada(pc, "preventivo", date(2026, 3, 5))
        correctivo = _cerrada(pc, "correctivo", date(2026, 8, 1))
        self.assertEqual(situacion(pc, HOY).ultimo, correctivo)


class TableroTests(TestCase):
    def test_solo_tipos_con_checklist_y_sin_dados_de_baja(self):
        incluidos = {crear_pc("A").pk, crear_pc("B", tipo="escritorio").pk}
        crear_pc("C", tipo="celular")
        crear_pc("D", estado="dado_de_baja")
        self.assertEqual(set(activos_programables().values_list("pk", flat=True)), incluidos)

    def test_por_hacer_incluye_proximos_30_dias_y_ordena(self):
        crear_pc("A", compra=date(2023, 1, 10), meses=12)  # le toca desde 2024
        b = crear_pc("B", compra=date(2025, 10, 1), meses=24)
        ProgramacionMantenimiento.objects.create(activo=b, fecha_programada=date(2026, 11, 1))
        c = crear_pc("C", compra=date(2020, 1, 1), meses=12)
        _cerrada(c, "preventivo", date(2025, 11, 10))  # le toca 2026-11-10
        d = crear_pc("D", compra=date(2020, 1, 1), meses=12)
        _cerrada(d, "preventivo", date(2026, 5, 1))  # le toca 2027-05-01
        crear_pc("E", compra=date(2025, 10, 1), meses=24)  # en garantía
        t = tablero(HOY)
        self.assertEqual([s.activo.serial for s in t["por_hacer"]], ["A", "B", "C"])
        self.assertEqual([s.activo.serial for s in t["al_dia"]], ["D"])
        self.assertEqual([s.activo.serial for s in t["en_garantia"]], ["E"])
        self.assertEqual(t["conteos"], {"programado": 1, "le_toca": 1, "en_garantia": 1, "al_dia": 2})


class ProximoPreventivoTests(TestCase):
    def test_completo_en_garantia_y_correctivo(self):
        pc = crear_pc(compra=date(2025, 10, 1), meses=24)
        self.assertEqual(proximo_preventivo(_cerrada(pc, "preventivo", date(2026, 10, 23))), date(2027, 10, 23))
        self.assertEqual(
            proximo_preventivo(_cerrada(pc, "preventivo", date(2026, 5, 1), en_garantia=True)),
            date(2027, 10, 1),
        )
        self.assertIsNone(proximo_preventivo(_cerrada(pc, "correctivo", date(2026, 5, 1))))

    def test_orden_nueva_es_formato_actual(self):
        self.assertEqual(_cerrada(crear_pc(), "correctivo", HOY).formato, 2)


class MigracionFormatoTests(TestCase):
    def test_las_ordenes_existentes_pasan_a_formato_anterior(self):
        orden = _cerrada(crear_pc(), "correctivo", HOY)
        self.assertEqual(orden.formato, FORMATO_ACTUAL)
        migracion = import_module("mantenimiento.migrations.0011_programacion_y_formato")
        migracion.marcar_ordenes_existentes(apps, None)
        orden.refresh_from_db()
        self.assertEqual(orden.formato, FORMATO_ANTERIOR)
