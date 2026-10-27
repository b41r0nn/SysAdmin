from datetime import date, timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventario.models import Activo
from mantenimiento.ayudas_pruebas import asignar, crear_pc, crear_usuario
from mantenimiento.ejecucion import (
    campos_equipo,
    cerrar_orden,
    errores_para_cerrar,
    iniciar_preventivo,
    marcar_punto,
    reabrir_orden,
)
from mantenimiento.models import ChecklistItem, OrdenMantenimiento, ProgramacionMantenimiento

HOY = date(2026, 10, 23)


def _sin_ocs():
    return patch("mantenimiento.ejecucion.snapshot_software_ocs", return_value=[])


def _marcar_todo(orden, resultado="bien"):
    for item in orden.checklist_items.all():
        marcar_punto(item, resultado, "x" if resultado == "falla" else "")


class CerrarTests(TestCase):
    def setUp(self):
        p = _sin_ocs()
        p.start()
        self.addCleanup(p.stop)
        self.tecnico = crear_usuario(first_name="Ana", last_name="Técnica", cargo="Analista de Sistemas")
        self.pc = crear_pc(compra=date(2023, 1, 1), meses=12, nombre_equipo="PT-12", ip_equipo="192.168.1.57")
        self.orden = iniciar_preventivo(self.pc, self.tecnico, HOY)

    def _marcar_todo(self, resultado="bien"):
        _marcar_todo(self.orden, resultado)

    def _cerrar(self, **kw):
        datos = {"fecha_cierre": HOY, "estado_final": "operativo", "observaciones": "", "hoy": HOY} | kw
        cerrar_orden(self.orden, self.tecnico, **datos)

    def test_no_cierra_con_puntos_pendientes(self):
        with self.assertRaisesMessage(ValidationError, "Quedan puntos del checklist sin marcar (12)."):
            self._cerrar()

    def test_cierra_y_congela_datos_del_acta(self):
        asignar(self.pc)
        self._marcar_todo()
        self._cerrar()
        self.orden.refresh_from_db()
        self.assertEqual((self.orden.estado, self.orden.tecnico), ("cerrada", self.tecnico))
        d = self.orden.datos_acta
        self.assertEqual(d["tipo_acta"], "Preventivo")
        self.assertEqual(d["titulo"], "ACTA DE MANTENIMIENTO DE EQUIPOS DE CÓMPUTO")
        self.assertEqual(d["responsable"], {"nombre": "Marta López Gómez", "documento": "200300400", "cargo": "Contadora", "area": "Finanzas"})
        self.assertEqual(d["tecnico"], {"nombre": "Ana Técnica", "cargo": "Analista de Sistemas"})
        self.assertIn(["IP", "192.168.1.57"], d["campos"])
        self.assertEqual(d["proximo"], "23/10/2027")
        Activo.objects.filter(pk=self.pc.pk).update(ip_equipo="10.0.0.9")
        self.orden.refresh_from_db()
        self.assertIn(["IP", "192.168.1.57"], self.orden.datos_acta["campos"])

    def test_guarda_fecha_estado_final_y_observaciones(self):
        self._marcar_todo()
        self._cerrar(estado_final="operativo_obs", observaciones="  Cambiar batería pronto.  ")
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.fecha_cierre, HOY)
        self.assertEqual(self.orden.estado_final, "operativo_obs")
        self.assertEqual(self.orden.observaciones, "Cambiar batería pronto.")
        self.assertEqual(self.orden.tecnico_asignado, "")

    def test_sin_responsable_queda_none(self):
        self._marcar_todo()
        self._cerrar()
        self.orden.refresh_from_db()
        self.assertIsNone(self.orden.datos_acta["responsable"])

    def test_cerrar_limpia_la_fecha_programada(self):
        ProgramacionMantenimiento.objects.create(activo=self.pc, fecha_programada=HOY + timedelta(days=5))
        self._marcar_todo()
        self._cerrar()
        self.assertIsNone(ProgramacionMantenimiento.objects.get(activo=self.pc).fecha_programada)

    def test_en_garantia_tipo_acta_y_proximo(self):
        pc = crear_pc("SN-GAR", compra=date(2026, 1, 1), meses=24)
        orden = iniciar_preventivo(pc, self.tecnico, HOY)
        _marcar_todo(orden)
        cerrar_orden(orden, self.tecnico, fecha_cierre=HOY, estado_final="operativo", observaciones="", hoy=HOY)
        orden.refresh_from_db()
        self.assertEqual(orden.datos_acta["tipo_acta"], "Preventivo en garantía")
        self.assertEqual(orden.datos_acta["proximo"], "01/01/2028")
        self.assertEqual(orden.datos_acta["garantia"], "Hasta 01/01/2028")

    def test_garantia_vencida_y_sin_dato(self):
        self._marcar_todo()
        self._cerrar()
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.datos_acta["garantia"], "Vencida 01/01/2024")

        pc = crear_pc("SN-SIN-COMPRA")
        orden = iniciar_preventivo(pc, self.tecnico, HOY)
        _marcar_todo(orden)
        cerrar_orden(orden, self.tecnico, fecha_cierre=HOY, estado_final="operativo", observaciones="", hoy=HOY)
        orden.refresh_from_db()
        self.assertEqual(orden.datos_acta["garantia"], "Sin dato")

    def test_cerrar_dos_veces(self):
        self._marcar_todo()
        self._cerrar()
        with self.assertRaisesMessage(ValidationError, "El mantenimiento ya está cerrado."):
            self._cerrar()
        # Ya cerrado, es el único error aunque los demás datos también estén mal.
        self.orden.refresh_from_db()
        errores = errores_para_cerrar(
            self.orden, fecha_cierre=HOY + timedelta(days=1), estado_final="", observaciones="x" * 601, hoy=HOY
        )
        self.assertEqual(errores, ["El mantenimiento ya está cerrado."])

    def test_fecha_de_cierre_futura(self):
        self._marcar_todo()
        with self.assertRaisesMessage(ValidationError, "La fecha de cierre no puede ser futura."):
            self._cerrar(fecha_cierre=HOY + timedelta(days=1))
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, "en_proceso")

    def test_fecha_de_cierre_anterior_a_la_apertura(self):
        self._marcar_todo()
        with self.assertRaisesMessage(ValidationError, "La fecha de cierre no puede ser anterior a la apertura."):
            self._cerrar(fecha_cierre=HOY - timedelta(days=1))

    def test_observaciones_maximo_600(self):
        self._marcar_todo()
        with self.assertRaisesMessage(ValidationError, "Las observaciones no pueden pasar de 600 caracteres."):
            self._cerrar(observaciones="x" * 601)
        self._cerrar(observaciones="x" * 600)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, "cerrada")

    def test_falla_sin_observacion_no_cierra(self):
        self._marcar_todo()
        ChecklistItem.objects.filter(orden=self.orden, descripcion="Bisagras").update(resultado="falla", observacion="")
        with self.assertRaisesMessage(ValidationError, "Cada falla necesita su observación."):
            self._cerrar()

    def test_errores_en_orden(self):
        errores = errores_para_cerrar(
            self.orden, fecha_cierre=HOY + timedelta(days=1), estado_final="", observaciones="x" * 601, hoy=HOY
        )
        self.assertEqual(errores, [
            "La fecha de cierre no puede ser futura.",
            "Elige el estado final del equipo.",
            "Las observaciones no pueden pasar de 600 caracteres.",
            "Quedan puntos del checklist sin marcar (12).",
        ])

    def test_correctivo_exige_diagnostico_y_solucion(self):
        asignar(self.pc)
        orden = OrdenMantenimiento.objects.create(activo=self.pc, tipo="correctivo", estado="abierta", fecha_apertura=HOY)
        base = {"fecha_cierre": HOY, "estado_final": "fuera_servicio", "observaciones": "", "hoy": HOY}
        self.assertEqual(errores_para_cerrar(orden, **base, diagnostico=" ", acciones=""), [
            "Escribe el diagnóstico.",
            "Escribe la solución o las acciones realizadas.",
        ])
        self.assertEqual(errores_para_cerrar(orden, **base, diagnostico="x" * 601, acciones="x" * 601), [
            "El diagnóstico no puede pasar de 600 caracteres.",
            "La solución no puede pasar de 600 caracteres.",
        ])
        cerrar_orden(orden, self.tecnico, **base, diagnostico="Disco dañado", acciones="Se cambió el disco")
        orden.refresh_from_db()
        self.assertEqual((orden.estado, orden.diagnostico, orden.acciones), ("cerrada", "Disco dañado", "Se cambió el disco"))
        self.assertEqual(orden.datos_acta["tipo_acta"], "Correctivo")
        self.assertEqual(orden.datos_acta["proximo"], "")
        self.assertEqual(orden.datos_acta["responsable"]["nombre"], "Marta López Gómez")

    def test_correctivo_no_toca_la_fecha_programada(self):
        ProgramacionMantenimiento.objects.create(activo=self.pc, fecha_programada=HOY + timedelta(days=5))
        orden = OrdenMantenimiento.objects.create(activo=self.pc, tipo="correctivo", estado="abierta", fecha_apertura=HOY)
        cerrar_orden(orden, self.tecnico, fecha_cierre=HOY, estado_final="operativo", observaciones="",
                     diagnostico="Teclado", acciones="Se cambió el teclado", hoy=HOY)
        self.assertEqual(ProgramacionMantenimiento.objects.get(activo=self.pc).fecha_programada, HOY + timedelta(days=5))

    def test_reabrir_marca_acta_firmada_desactualizada(self):
        self._marcar_todo()
        self._cerrar()
        OrdenMantenimiento.objects.filter(pk=self.orden.pk).update(acta_firmada="mantenimiento/actas/acta-1.pdf")
        self.orden.refresh_from_db()
        reabrir_orden(self.orden)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, "en_proceso")
        self.assertIsNone(self.orden.fecha_cierre)
        self.assertEqual(self.orden.datos_acta, {})
        self.assertTrue(self.orden.acta_firmada_desactualizada)
        self.assertEqual(self.orden.acta_firmada.name, "mantenimiento/actas/acta-1.pdf")

    def test_reabrir_sin_acta_firmada(self):
        self._marcar_todo()
        self._cerrar()
        reabrir_orden(self.orden)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, "en_proceso")
        self.assertFalse(self.orden.acta_firmada_desactualizada)

    def test_reabrir_solo_si_esta_cerrada(self):
        with self.assertRaisesMessage(ValidationError, "El mantenimiento no está cerrado."):
            reabrir_orden(self.orden)


class CamposEquipoTests(TestCase):
    def test_por_tipo(self):
        etiquetas = [e for e, _ in campos_equipo(crear_pc("SN-PT"))]
        self.assertIn("Procesador", etiquetas)
        self.assertEqual(etiquetas[-1], "Ubicación")

        celular = [e for e, _ in campos_equipo(crear_pc("SN-CEL", tipo="celular", imei="356789012345678"))]
        self.assertIn("IMEI", celular)
        self.assertNotIn("Procesador", celular)

        diadema = campos_equipo(crear_pc("SN-DIA", tipo="Diadema"))
        self.assertEqual([e for e, _ in diadema], ["Equipo", "Marca/modelo", "Serial", "N° interno", "Ubicación"])
        self.assertEqual(diadema[0], ["Equipo", "Diadema"])
        self.assertEqual(diadema[1], ["Marca/modelo", "HP ProBook"])
        self.assertEqual(diadema[-1], ["Ubicación", "—"])

    def test_campos_de_portatil(self):
        pc = crear_pc("SN-PT2", nombre_equipo="PT-07", procesador="Intel Core i5", ram="16 GB",
                      disco_capacidad="512 GB", tipo_disco="SSD", sistema_operativo="Windows 11",
                      ip_equipo="192.168.1.20", ubicacion_fisica="Oficina 2")
        campos = dict(campos_equipo(pc))
        self.assertEqual(campos["Nombre"], "PT-07")
        self.assertEqual(campos["Disco"], "512 GB SSD")
        self.assertEqual(campos["S.O."], "Windows 11")
        self.assertEqual(campos["IP"], "192.168.1.20")
        self.assertEqual(campos["Ubicación"], "Oficina 2")
        self.assertEqual(campos["N° interno"], str(pc.numero_interno))

    def test_telefono_y_monitor(self):
        tel = dict(campos_equipo(crear_pc("SN-TEL", tipo="telefono_fijo", extension="105")))
        self.assertEqual((tel["Extensión"], tel["Línea"]), ("105", "—"))
        mon = dict(campos_equipo(crear_pc("SN-MON", tipo="monitor", pulgadas="24.0", resolucion="1920x1080")))
        self.assertEqual((mon["Pulgadas"], mon["Resolución"]), ("24", "1920x1080"))


class VistaCerrarTests(TestCase):
    def setUp(self):
        p = _sin_ocs()
        p.start()
        self.addCleanup(p.stop)
        self.hoy = timezone.localdate()
        self.pc = crear_pc()
        self.orden = iniciar_preventivo(self.pc, crear_usuario())
        _marcar_todo(self.orden)

    def _url(self, nombre, orden=None):
        return reverse(f"mantenimiento:{nombre}", args=[(orden or self.orden).pk])

    def _datos(self, **kw):
        return {"fecha_cierre": self.hoy.isoformat(), "estado_final": "operativo", "observaciones": ""} | kw

    def test_pide_nombre_y_cargo_si_la_cuenta_no_tiene_nombre(self):
        cuenta = crear_usuario()
        self.client.force_login(cuenta)
        resp = self.client.get(self._url("cerrar_orden"))
        self.assertContains(resp, 'name="first_name"')
        self.assertContains(resp, 'name="cargo"')

        resp = self.client.post(self._url("cerrar_orden"), self._datos(
            first_name="Luis", last_name="Pérez Ruiz", cargo="Técnico de soporte"))
        self.assertRedirects(resp, self._url("detalle_orden"))
        cuenta.refresh_from_db()
        self.assertEqual((cuenta.first_name, cuenta.last_name, cuenta.cargo), ("Luis", "Pérez Ruiz", "Técnico de soporte"))
        self.orden.refresh_from_db()
        self.assertEqual((self.orden.estado, self.orden.tecnico), ("cerrada", cuenta))
        self.assertEqual(self.orden.datos_acta["tecnico"], {"nombre": "Luis Pérez Ruiz", "cargo": "Técnico de soporte"})

    def test_nombre_y_cargo_son_obligatorios_si_se_piden(self):
        self.client.force_login(crear_usuario())
        resp = self.client.post(self._url("cerrar_orden"), self._datos(first_name="", last_name="", cargo=""))
        self.assertEqual(resp.status_code, 200)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, "en_proceso")

    def test_no_pide_nombre_si_ya_lo_tiene(self):
        cuenta = crear_usuario(first_name="Ana", last_name="Técnica", cargo="Analista de Sistemas")
        self.client.force_login(cuenta)
        resp = self.client.get(self._url("cerrar_orden"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'name="first_name"')
        resp = self.client.post(self._url("cerrar_orden"), self._datos())
        self.assertRedirects(resp, self._url("detalle_orden"))
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, "cerrada")

    def test_errores_se_muestran_sin_cerrar(self):
        cuenta = crear_usuario()
        self.client.force_login(cuenta)
        orden = iniciar_preventivo(crear_pc("SN-PENDIENTE"), cuenta)
        resp = self.client.post(self._url("cerrar_orden", orden), self._datos(
            first_name="Luis", last_name="Pérez", cargo="Técnico"))
        self.assertContains(resp, "Quedan puntos del checklist sin marcar (12).")
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "en_proceso")
        # Si no se pudo cerrar, tampoco se guardan el nombre y el cargo.
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.get_full_name(), "")

    def test_correctivo_pide_diagnostico_y_solucion(self):
        self.client.force_login(crear_usuario(first_name="Ana", last_name="Técnica"))
        orden = OrdenMantenimiento.objects.create(activo=self.pc, tipo="correctivo", estado="abierta",
                                                  fecha_apertura=self.hoy)
        resp = self.client.get(self._url("cerrar_orden", orden))
        self.assertContains(resp, 'name="diagnostico"')
        self.assertContains(resp, 'name="acciones"')
        resp = self.client.post(self._url("cerrar_orden", orden), self._datos(diagnostico="Pantalla rota",
                                                                             acciones="Se cambió la pantalla"))
        self.assertRedirects(resp, self._url("detalle_orden", orden))
        orden.refresh_from_db()
        self.assertEqual((orden.estado, orden.diagnostico), ("cerrada", "Pantalla rota"))

    def test_cerrar_orden_cerrada_redirige(self):
        cuenta = crear_usuario(first_name="Ana", last_name="Técnica")
        self.client.force_login(cuenta)
        cerrar_orden(self.orden, cuenta, fecha_cierre=self.hoy, estado_final="operativo", observaciones="")
        resp = self.client.get(self._url("cerrar_orden"))
        self.assertRedirects(resp, self._url("detalle_orden"))

    def test_orden_cerrada_no_se_edita(self):
        cuenta = crear_usuario(first_name="Ana", last_name="Técnica")
        self.client.force_login(cuenta)
        cerrar_orden(self.orden, cuenta, fecha_cierre=self.hoy, estado_final="operativo", observaciones="")
        resp = self.client.get(self._url("editar_orden"))
        self.assertRedirects(resp, self._url("detalle_orden"))
        resp = self.client.post(self._url("editar_orden"), {"tipo": "correctivo"})
        self.assertRedirects(resp, self._url("detalle_orden"))
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.tipo, "preventivo")

    def test_detalle_de_cerrada_muestra_cierre_y_reabrir(self):
        cuenta = crear_usuario(first_name="Ana", last_name="Técnica", cargo="Analista de Sistemas")
        self.client.force_login(cuenta)
        cerrar_orden(self.orden, cuenta, fecha_cierre=self.hoy, estado_final="operativo_obs",
                     observaciones="Batería al 60 %.")
        resp = self.client.get(self._url("detalle_orden"))
        self.assertContains(resp, "Operativo con observaciones")
        self.assertContains(resp, "Batería al 60 %.")
        self.assertContains(resp, "Ana Técnica")
        self.assertContains(resp, self._url("reabrir_orden"))
        self.assertNotContains(resp, self._url("cerrar_orden"))

    def test_detalle_abierta_enlaza_al_cierre(self):
        self.client.force_login(crear_usuario())
        resp = self.client.get(self._url("detalle_orden"))
        self.assertContains(resp, f'href="{self._url("cerrar_orden")}"')
        self.assertNotContains(resp, self._url("reabrir_orden"))

    def test_reabrir_requiere_escritura(self):
        cuenta = crear_usuario(first_name="Ana", last_name="Técnica")
        cerrar_orden(self.orden, cuenta, fecha_cierre=self.hoy, estado_final="operativo", observaciones="")

        self.client.force_login(crear_usuario("lectura"))
        resp = self.client.post(self._url("reabrir_orden"))
        self.assertRedirects(resp, reverse("core:dashboard"), fetch_redirect_response=False)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, "cerrada")

        self.client.force_login(cuenta)
        self.assertEqual(self.client.get(self._url("reabrir_orden")).status_code, 405)
        resp = self.client.post(self._url("reabrir_orden"))
        self.assertRedirects(resp, self._url("detalle_orden"))
        self.orden.refresh_from_db()
        self.assertEqual((self.orden.estado, self.orden.datos_acta), ("en_proceso", {}))

    def test_cerrar_requiere_escritura(self):
        self.client.force_login(crear_usuario("lectura"))
        resp = self.client.post(self._url("cerrar_orden"), self._datos())
        self.assertRedirects(resp, reverse("core:dashboard"), fetch_redirect_response=False)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, "en_proceso")
