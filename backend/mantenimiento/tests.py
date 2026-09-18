from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from inventario.models import Activo
from mantenimiento.forms import ReporteFallaForm
from mantenimiento.models import (
    ChecklistItem,
    FotoMantenimiento,
    OrdenMantenimiento,
    PlanMantenimiento,
    Repuesto,
)
from notificaciones.models import Notificacion

CustomUser = get_user_model()

HOY = timezone.localdate()


def _user(rol):
    return CustomUser.objects.create_user(
        username=f"mtto_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


def _activo(serial="SN-MT-001"):
    return Activo.objects.create(
        serial=serial,
        tipo_dispositivo="escritorio",
        marca="HP",
        modelo="Pro",
        estado="disponible",
    )


def _plan(tipo_dispositivo="escritorio", **kw):
    defaults = {"tipo": "preventivo", "estado": "activo"}
    defaults.update(kw)
    return PlanMantenimiento.objects.create(tipo_dispositivo=tipo_dispositivo, **defaults)


def _orden(activo, **kw):
    defaults = {
        "tipo": "correctivo",
        "estado": "abierta",
        "prioridad": "media",
        "fecha_apertura": HOY,
    }
    defaults.update(kw)
    return OrdenMantenimiento.objects.create(activo=activo, **defaults)


# ─── Planes ────────────────────────────────────────────────────────


class PlanesLoginTests(TestCase):
    def test_lista_requiere_login(self):
        resp = self.client.get(reverse("mantenimiento:lista_planes"))
        self.assertEqual(resp.status_code, 302)


class PlanesCRUDTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_lista_returns_200(self):
        resp = self.client.get(reverse("mantenimiento:lista_planes"))
        self.assertEqual(resp.status_code, 200)

    def test_detalle_returns_200(self):
        p = _plan()
        resp = self.client.get(reverse("mantenimiento:detalle_plan", args=[p.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_crear_plan_post(self):
        resp = self.client.post(
            reverse("mantenimiento:crear_plan"),
            {
                "tipo_dispositivo": "escritorio",
                "tipo": "preventivo",
                "criticidad": "alta",
                "frecuencia_dias": 30,
                "estado": "activo",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(PlanMantenimiento.objects.filter(tipo_dispositivo="escritorio").exists())

    def test_toggle_plan(self):
        p = _plan(estado="activo")
        resp = self.client.post(reverse("mantenimiento:toggle_plan", args=[p.pk]))
        self.assertEqual(resp.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.estado, "pausado")

    def test_eliminar_plan_sin_ordenes(self):
        p = _plan()
        resp = self.client.post(reverse("mantenimiento:eliminar_plan", args=[p.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PlanMantenimiento.objects.filter(pk=p.pk).exists())

    def test_eliminar_plan_con_ordenes_fallido(self):
        p = _plan()
        _orden(self.activo, plan=p)
        resp = self.client.post(reverse("mantenimiento:eliminar_plan", args=[p.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(PlanMantenimiento.objects.filter(pk=p.pk).exists())


class PlanesPermisosTests(TestCase):
    def test_lectura_no_puede_crear(self):
        user = _user("lectura")
        self.client.force_login(user)
        resp = self.client.get(reverse("mantenimiento:crear_plan"))
        self.assertEqual(resp.status_code, 302)


# ─── Ordenes ───────────────────────────────────────────────────────


class OrdenesCRUDTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_lista_ordenes_returns_200(self):
        resp = self.client.get(reverse("mantenimiento:lista_ordenes"))
        self.assertEqual(resp.status_code, 200)

    def test_detalle_orden_returns_200(self):
        o = _orden(self.activo)
        resp = self.client.get(reverse("mantenimiento:detalle_orden", args=[o.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_crear_orden_post(self):
        resp = self.client.post(
            reverse("mantenimiento:crear_orden"),
            {
                "activo": self.activo.pk,
                "tipo": "correctivo",
                "estado": "abierta",
                "prioridad": "alta",
                "fecha_apertura": HOY,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(OrdenMantenimiento.objects.filter(activo=self.activo).exists())

    def test_cerrar_orden(self):
        o = _orden(self.activo, estado="abierta")
        resp = self.client.post(reverse("mantenimiento:cerrar_orden", args=[o.pk]))
        self.assertEqual(resp.status_code, 302)
        o.refresh_from_db()
        self.assertEqual(o.estado, "cerrada")
        self.assertIsNotNone(o.fecha_cierre)

    def test_cerrar_orden_ya_cerrada(self):
        o = _orden(self.activo, estado="cerrada", fecha_cierre=HOY)
        resp = self.client.post(reverse("mantenimiento:cerrar_orden", args=[o.pk]))
        self.assertEqual(resp.status_code, 302)
        o.refresh_from_db()
        self.assertEqual(o.estado, "cerrada")

    def test_eliminar_orden(self):
        o = _orden(self.activo)
        resp = self.client.post(reverse("mantenimiento:eliminar_orden", args=[o.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(OrdenMantenimiento.objects.filter(pk=o.pk).exists())


class RepuestosTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()
        self.orden = _orden(self.activo)

    def test_crear_repuesto_post(self):
        resp = self.client.post(
            reverse("mantenimiento:crear_repuesto", args=[self.orden.pk]),
            {
                "orden": self.orden.pk,
                "nombre": "Filtro",
                "cantidad": 2,
                "costo_unitario": 15000,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Repuesto.objects.filter(orden=self.orden).exists())

    def test_editar_repuesto(self):
        r = Repuesto.objects.create(
            orden=self.orden, nombre="Filtro", cantidad=1, costo_unitario=10000
        )
        resp = self.client.post(
            reverse("mantenimiento:editar_repuesto", args=[r.pk]),
            {
                "orden": self.orden.pk,
                "nombre": "Filtro Pro",
                "cantidad": 3,
                "costo_unitario": 20000,
            },
        )
        self.assertEqual(resp.status_code, 302)
        r.refresh_from_db()
        self.assertEqual(r.nombre, "Filtro Pro")

    def test_eliminar_repuesto(self):
        r = Repuesto.objects.create(
            orden=self.orden, nombre="Filtro", cantidad=1, costo_unitario=10000
        )
        resp = self.client.post(reverse("mantenimiento:eliminar_repuesto", args=[r.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Repuesto.objects.filter(pk=r.pk).exists())


# ─── Fase 3: Checklist ─────────────────────────────────────────────


class ChecklistTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def _plan_con_checklist(self, descripciones):
        plan = _plan()
        for i, d in enumerate(descripciones):
            ChecklistItem.objects.create(plan=plan, descripcion=d, posicion=i)
        return plan

    def test_crear_orden_copia_checklist_del_plan_sin_completar(self):
        plan = self._plan_con_checklist(
            ["Inspeccion visual", "Pruebas de encendido", "Limpieza de ventiladores"]
        )
        resp = self.client.post(
            reverse("mantenimiento:crear_orden"),
            {
                "plan": plan.pk,
                "activo": self.activo.pk,
                "tipo": "preventivo",
                "estado": "abierta",
                "prioridad": "media",
                "fecha_apertura": HOY,
            },
        )
        self.assertEqual(resp.status_code, 302)
        orden = OrdenMantenimiento.objects.get(plan=plan)
        items = orden.checklist_items.all().order_by("posicion")
        self.assertEqual(items.count(), 3)
        self.assertEqual(
            list(items.values_list("descripcion", flat=True)),
            ["Inspeccion visual", "Pruebas de encendido", "Limpieza de ventiladores"],
        )
        self.assertFalse(any(i.completado for i in items))

    def test_crear_orden_sin_plan_no_genera_items(self):
        resp = self.client.post(
            reverse("mantenimiento:crear_orden"),
            {
                "activo": self.activo.pk,
                "tipo": "correctivo",
                "estado": "abierta",
                "prioridad": "alta",
                "fecha_apertura": HOY,
            },
        )
        self.assertEqual(resp.status_code, 302)
        orden = OrdenMantenimiento.objects.get(activo=self.activo)
        self.assertEqual(orden.checklist_items.count(), 0)

    def test_toggle_checklist_marca_y_desmarca(self):
        plan = self._plan_con_checklist(["Inspeccion visual"])
        orden = _orden(self.activo, plan=plan)
        item = ChecklistItem.objects.create(orden=orden, descripcion="Inspeccion visual")

        resp = self.client.post(reverse("mantenimiento:toggle_checklist", args=[item.pk]))
        self.assertEqual(resp.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.completado)

        resp = self.client.post(reverse("mantenimiento:toggle_checklist", args=[item.pk]))
        self.assertEqual(resp.status_code, 200)
        item.refresh_from_db()
        self.assertFalse(item.completado)

    def test_plantilla_del_plan_no_usa_estado_orden(self):
        plan = self._plan_con_checklist(["A", "B", "C"])
        self.assertEqual(plan.checklist_items.filter(orden__isnull=True).count(), 3)


# ─── Fase 3: Command notificaciones ────────────────────────────────


class CommandNotificacionesMantenimientoTests(TestCase):
    def setUp(self):
        self.activo = _activo()

    def test_idempotente_y_una_por_usuario_con_permiso(self):
        user_super = _user("superadmin")
        user_tecnico = _user("tecnico")
        user_lectura = _user("lectura")
        plan = _plan(proxima_ejecucion=HOY + timedelta(days=3))

        call_command("generar_notificaciones_mantenimiento")
        call_command("generar_notificaciones_mantenimiento")

        for user in (user_super, user_tecnico, user_lectura):
            notif = list(
                user.notificaciones.filter(tipo="mantenimiento", objetokey=f"mantenimiento:{plan.pk}")
            )
            self.assertEqual(len(notif), 1)


# ─── Fase 3: Portal de reporte y calendario ────────────────────────


class ReporteFallaPortalTests(TestCase):
    def setUp(self):
        self.activo = _activo()

    def test_requiere_login(self):
        resp = self.client.get(reverse("mantenimiento:reportar"))
        self.assertEqual(resp.status_code, 302)

    def test_lectura_puede_reportar(self):
        user = _user("lectura")
        self.client.force_login(user)

        resp = self.client.get(reverse("mantenimiento:reportar"))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(
            reverse("mantenimiento:reportar"),
            {
                "activo": self.activo.pk,
                "prioridad": "alta",
                "descripcion": "El equipo no enciende.",
            },
        )
        self.assertEqual(resp.status_code, 302)
        orden = OrdenMantenimiento.objects.get(activo=self.activo)
        self.assertEqual(orden.estado, "reportada")
        self.assertEqual(orden.tipo, "correctivo")
        self.assertEqual(orden.prioridad, "alta")
        self.assertEqual(orden.fecha_apertura, HOY)
        self.assertEqual(orden.reportado_por, user)

    def test_reporte_genera_notificacion_a_tecnico(self):
        user = _user("lectura")
        tecnico = _user("tecnico")
        self.client.force_login(user)

        self.client.post(
            reverse("mantenimiento:reportar"),
            {"activo": self.activo.pk, "prioridad": "media", "descripcion": "Falla."},
        )
        self.assertTrue(
            Notificacion.objects.filter(
                usuario=tecnico, tipo="aviso", objetokey__startswith="orden:"
            ).exists()
        )

    def test_lectura_no_puede_crear_orden_completa(self):
        user = _user("lectura")
        self.client.force_login(user)
        resp = self.client.get(reverse("mantenimiento:crear_orden"))
        self.assertEqual(resp.status_code, 302)

    def test_reporte_invalido_no_crea_orden(self):
        user = _user("lectura")
        self.client.force_login(user)
        resp = self.client.post(
            reverse("mantenimiento:reportar"),
            {"prioridad": "alta", "descripcion": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(OrdenMantenimiento.objects.count(), 0)


# ─── Reporte robusto: foto y activos activos ───────────────────────


class ReporteFallaFotoTests(TestCase):
    def setUp(self):
        self.user = _user("lectura")
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_post_con_foto_guarda_imagen(self):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
        foto = SimpleUploadedFile("falla.png", buf.getvalue(), content_type="image/png")
        resp = self.client.post(
            reverse("mantenimiento:reportar"),
            {"activo": self.activo.pk, "prioridad": "alta", "descripcion": "Falla.", "foto": foto},
        )
        self.assertEqual(resp.status_code, 302)
        orden = OrdenMantenimiento.objects.get(activo=self.activo)
        self.assertTrue(orden.foto.name.startswith("mantenimiento/fotos/"))

    def test_activo_dado_de_baja_no_es_opcion(self):
        self.activo.estado = "dado_de_baja"
        self.activo.save()
        resp = self.client.post(
            reverse("mantenimiento:reportar"),
            {"activo": self.activo.pk, "prioridad": "media", "descripcion": "Intento."},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(OrdenMantenimiento.objects.count(), 0)

    def test_form_rechaza_activo_dado_de_baja(self):
        self.activo.estado = "dado_de_baja"
        self.activo.save()
        form = ReporteFallaForm(
            data={"activo": self.activo.pk, "prioridad": "media", "descripcion": "x"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("activo", form.errors)

    def test_reporte_encola_email_a_tecnicos(self):
        tecnico = _user("tecnico")
        tecnico.email = "tecnico@test.com"
        tecnico.save(update_fields=["email"])
        with patch("mantenimiento.views.encolar_email") as mock:
            self.client.post(
                reverse("mantenimiento:reportar"),
                {"activo": self.activo.pk, "prioridad": "media", "descripcion": "Falla."},
            )
        self.assertTrue(mock.called)
        asuntos = [call.args[0] for call in mock.call_args_list]
        self.assertTrue(all(asuntos))


class CalendarioTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_calendario_returns_200(self):
        resp = self.client.get(reverse("mantenimiento:calendario"))
        self.assertEqual(resp.status_code, 200)

    def test_eventos_incluyen_ordenes_y_planes(self):
        orden = _orden(self.activo, tipo="correctivo", estado="abierta")
        plan = _plan(tipo="preventivo", proxima_ejecucion=HOY + timedelta(days=5))
        resp = self.client.get(reverse("mantenimiento:calendario_eventos"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        titulos = [e["title"] for e in data]
        self.assertTrue(any(f"Orden #{orden.id}" in t for t in titulos))
        self.assertTrue(any(f"Plan Preventivo" in t for t in titulos))


# ─── Fase 4: Snapshot software + fotos + hoja de vida ─────────────


class FakeWeasyHTML:
    def __init__(self, *args, **kwargs):
        pass

    def write_pdf(self):
        return b"%PDF-1.4 fake-mantenimiento"


class FakeWeasyPrintModule:
    HTML = FakeWeasyHTML


class SoftwareSnapshotTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_crear_orden_guarda_software_del_textarea(self):
        resp = self.client.post(
            reverse("mantenimiento:crear_orden"),
            {
                "activo": self.activo.pk,
                "tipo": "correctivo",
                "estado": "abierta",
                "prioridad": "media",
                "fecha_apertura": HOY,
                "software_snapshot_text": "Google Chrome\nAdobe Acrobat",
            },
        )
        self.assertEqual(resp.status_code, 302)
        orden = OrdenMantenimiento.objects.get(activo=self.activo)
        self.assertEqual(orden.software_snapshot, ["Google Chrome", "Adobe Acrobat"])

    def test_editar_orden_precarga_software_existente(self):
        orden = _orden(self.activo)
        orden.software_snapshot = ["Google Chrome", "Word"]
        orden.save()
        resp = self.client.get(reverse("mantenimiento:editar_orden", args=[orden.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Google Chrome")
        self.assertContains(resp, "Word")

    def test_snapshot_ocs_vacio_sin_equipo_vinculado(self):
        from mantenimiento.services import snapshot_software_ocs

        self.assertEqual(snapshot_software_ocs(self.activo), [])


class FotoMantenimientoTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def _foto_bytes(self):
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
        return SimpleUploadedFile("mant.png", buf.getvalue(), content_type="image/png")

    def test_crear_orden_con_foto(self):
        resp = self.client.post(
            reverse("mantenimiento:crear_orden"),
            {
                "activo": self.activo.pk,
                "tipo": "correctivo",
                "estado": "abierta",
                "prioridad": "media",
                "fecha_apertura": HOY,
                "fotos-TOTAL_FORMS": "1",
                "fotos-INITIAL_FORMS": "0",
                "fotos-MIN_NUM_FORMS": "0",
                "fotos-MAX_NUM_FORMS": "1000",
                "fotos-0-foto": self._foto_bytes(),
                "fotos-0-descripcion": "Antes",
            },
        )
        self.assertEqual(resp.status_code, 302)
        orden = OrdenMantenimiento.objects.get(activo=self.activo)
        self.assertEqual(orden.fotos.count(), 1)
        self.assertEqual(orden.fotos.first().descripcion, "Antes")

    def test_detalle_orden_muestra_fotos(self):
        orden = _orden(self.activo)
        FotoMantenimiento.objects.create(
            orden=orden, foto=self._foto_bytes(), descripcion="Despues"
        )
        resp = self.client.get(reverse("mantenimiento:detalle_orden", args=[orden.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Despues")

    def test_eliminar_foto(self):
        orden = _orden(self.activo)
        foto = FotoMantenimiento.objects.create(
            orden=orden, foto=self._foto_bytes(), descripcion="X"
        )
        resp = self.client.post(reverse("mantenimiento:eliminar_foto", args=[foto.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(FotoMantenimiento.objects.filter(pk=foto.pk).exists())


class ChecklistEditableTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_crear_item_checklist_en_orden(self):
        orden = _orden(self.activo)
        resp = self.client.post(
            reverse("mantenimiento:crear_item_checklist", args=[orden.pk]),
            {"descripcion": "Verificar cableado"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            ChecklistItem.objects.filter(orden=orden, descripcion="Verificar cableado").exists()
        )


class OrdenAccionesYPartesTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo_portatil = Activo.objects.create(
            serial="SN-PT-001",
            tipo_dispositivo="portatil",
            marca="Lenovo",
            modelo="ThinkPad",
            estado="disponible",
        )

    def test_crear_orden_guarda_acciones_y_estado_partes(self):
        resp = self.client.post(
            reverse("mantenimiento:crear_orden"),
            {
                "activo": self.activo_portatil.pk,
                "tipo": "preventivo",
                "estado": "abierta",
                "prioridad": "media",
                "fecha_apertura": HOY,
                "accion_limpieza_general": "on",
                "accion_mantenimiento_logico": "on",
                "accion_cambio_parte": "on",
                "accion_cambio_parte_detalle": "Teclado completo",
                "parte_pantalla": "bien",
                "parte_teclado": "mal",
                "parte_bateria": "bien",
            },
        )
        self.assertEqual(resp.status_code, 302)
        orden = OrdenMantenimiento.objects.get(activo=self.activo_portatil)
        self.assertTrue(orden.accion_limpieza_general)
        self.assertTrue(orden.accion_mantenimiento_logico)
        self.assertFalse(orden.accion_cambio_pasta_termica)
        self.assertTrue(orden.accion_cambio_parte)
        self.assertEqual(orden.accion_cambio_parte_detalle, "Teclado completo")
        self.assertEqual(
            orden.estado_partes,
            {"pantalla": "bien", "teclado": "mal", "bateria": "bien"},
        )

    def test_cambio_parte_sin_detalle_devuelve_error(self):
        resp = self.client.post(
            reverse("mantenimiento:crear_orden"),
            {
                "activo": self.activo_portatil.pk,
                "tipo": "correctivo",
                "estado": "abierta",
                "prioridad": "alta",
                "fecha_apertura": HOY,
                "accion_cambio_parte": "on",
                "accion_cambio_parte_detalle": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(OrdenMantenimiento.objects.count(), 0)
        self.assertContains(resp, "Indicá qué parte se cambió")

    def test_partial_estado_partes_cambia_segun_tipo_activo(self):
        activo_monitor = Activo.objects.create(
            serial="SN-MN-001",
            tipo_dispositivo="monitor",
            marca="Dell",
            modelo="P2419",
            estado="disponible",
        )
        resp_portatil = self.client.get(
            reverse("mantenimiento:estado_partes_partial"),
            {"activo": self.activo_portatil.pk},
        )
        self.assertEqual(resp_portatil.status_code, 200)
        self.assertContains(resp_portatil, "Teclado")
        self.assertContains(resp_portatil, "Touchpad")

        resp_monitor = self.client.get(
            reverse("mantenimiento:estado_partes_partial"),
            {"activo": activo_monitor.pk},
        )
        self.assertEqual(resp_monitor.status_code, 200)
        self.assertContains(resp_monitor, "Puerto de video")
        self.assertNotContains(resp_monitor, "Teclado")


class HojaDeVidaTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_hoja_de_vida_returns_200(self):
        _orden(self.activo, estado="cerrada", fecha_cierre=HOY)
        resp = self.client.get(reverse("mantenimiento:hoja_de_vida", args=[self.activo.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.activo.serial)

    def test_hoja_de_vida_muestra_software_ultimo_snapshot(self):
        orden = _orden(self.activo, estado="cerrada", fecha_cierre=HOY)
        orden.software_snapshot = ["Google Chrome", "Word"]
        orden.save()
        resp = self.client.get(reverse("mantenimiento:hoja_de_vida", args=[self.activo.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Google Chrome")
        self.assertContains(resp, "Word")

    def test_hoja_de_vida_sin_mantenimientos(self):
        resp = self.client.get(reverse("mantenimiento:hoja_de_vida", args=[self.activo.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_hoja_de_vida_muestra_acciones_y_estado_partes(self):
        orden = _orden(self.activo, estado="cerrada", fecha_cierre=HOY)
        orden.accion_limpieza_general = True
        orden.accion_cambio_parte = True
        orden.accion_cambio_parte_detalle = "Disco duro"
        orden.estado_partes = {"disco_duro": "mal", "memoria_ram": "bien"}
        orden.save()
        resp = self.client.get(reverse("mantenimiento:hoja_de_vida", args=[self.activo.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Limpieza general")
        self.assertContains(resp, "Cambio de parte")
        self.assertContains(resp, "Disco duro")
        self.assertContains(resp, "Memoria RAM")


class PdfMantenimientoTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_orden_pdf_returns_pdf(self):
        orden = _orden(self.activo, estado="cerrada", fecha_cierre=HOY)
        with patch.dict("sys.modules", {"weasyprint": FakeWeasyPrintModule()}):
            resp = self.client.get(reverse("mantenimiento:orden_pdf", args=[orden.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_reporte_mantenimientos_pdf_returns_pdf(self):
        _orden(self.activo, estado="cerrada", fecha_cierre=HOY)
        with patch.dict("sys.modules", {"weasyprint": FakeWeasyPrintModule()}):
            resp = self.client.get(reverse("mantenimiento:reporte_mantenimientos_pdf"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_reporte_pdf_filtra_por_estado(self):
        orden = _orden(self.activo, estado="cerrada", fecha_cierre=HOY)
        with patch.dict("sys.modules", {"weasyprint": FakeWeasyPrintModule()}):
            resp = self.client.get(
                reverse("mantenimiento:reporte_mantenimientos_pdf"), {"estado": "cerrada"}
            )
        self.assertEqual(resp.status_code, 200)
        html = render_to_string(
            "mantenimiento/reporte_mantenimientos_pdf.html",
            {
                "ordenes": OrdenMantenimiento.objects.filter(estado="cerrada"),
                "config": None,
                "logo_path": "x",
                "generado": timezone.now(),
                "filtro_tipo": "",
                "filtro_estado": "cerrada",
                "filtro_inicio": "",
                "filtro_fin": "",
            },
        )
        self.assertIn(orden.activo.serial, html)


class HojaDeVidaBuscarTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = Activo.objects.create(
            serial="SN-HV-001",
            tipo_dispositivo="portatil",
            marca="Lenovo",
            modelo="ThinkPad",
            estado="disponible",
        )

    def test_buscar_pagina_devuelve_200(self):
        resp = self.client.get(reverse("mantenimiento:hoja_de_vida_buscar"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Buscar activo")

    def test_buscar_requiere_login(self):
        resp = Client().get(reverse("mantenimiento:hoja_de_vida_buscar"))
        self.assertEqual(resp.status_code, 302)

    def test_busqueda_htmx_por_serial_marca_y_modelo(self):
        headers = {"HTTP_HX_REQUEST": "true"}
        url = reverse("mantenimiento:hoja_de_vida_buscar")

        resp = self.client.get(url, {"q": "SN-HV-001"}, **headers)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "SN-HV-001")
        self.assertContains(resp, reverse("mantenimiento:hoja_de_vida", args=[self.activo.pk]))

        resp = self.client.get(url, {"q": "lenovo"}, **headers)
        self.assertContains(resp, "ThinkPad")

        resp = self.client.get(url, {"q": "thinkpad"}, **headers)
        self.assertContains(resp, "Lenovo")

        resp = self.client.get(url, {"q": "no-existe"}, **headers)
        self.assertContains(resp, "Sin resultados")


class HojaDeVidaPdfTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = Activo.objects.create(
            serial="SN-HV-PDF-001",
            tipo_dispositivo="portatil",
            marca="Lenovo",
            modelo="ThinkPad",
            estado="disponible",
        )

    def test_hoja_de_vida_pdf_returns_pdf(self):
        _orden(self.activo, estado="cerrada", fecha_cierre=HOY)
        with patch.dict("sys.modules", {"weasyprint": FakeWeasyPrintModule()}):
            resp = self.client.get(
                reverse("mantenimiento:hoja_de_vida_pdf", args=[self.activo.pk])
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))
        self.assertIn("hoja_de_vida_", resp["Content-Disposition"])

    def test_hoja_de_vida_pdf_template_contiene_historial_completo(self):
        orden = _orden(self.activo, estado="cerrada", fecha_cierre=HOY)
        orden.accion_limpieza_general = True
        orden.accion_cambio_parte = True
        orden.accion_cambio_parte_detalle = "Disco duro"
        orden.estado_partes = {"teclado": "mal", "bateria": "bien"}
        orden.software_snapshot = ["Google Chrome", "Word"]
        orden.save()
        foto = FotoMantenimiento.objects.create(
            orden=orden,
            descripcion="Antes del cambio",
            foto=SimpleUploadedFile(
                "mtto.jpg", b"%PDF fake image bytes", content_type="image/jpeg"
            ),
        )
        html = render_to_string("mantenimiento/hoja_de_vida_pdf.html", {
            "activo": self.activo,
            "ordenes_detalle": [{
                "orden": orden,
                "acciones": ["Limpieza general", "Cambio de parte"],
                "estado_partes": [("Teclado", "mal"), ("Batería", "bien")],
                "fotos": [{"path": foto.foto.path, "descripcion": "Antes del cambio"}],
            }],
            "ultima": orden,
            "asignacion_actual": None,
            "equipo_ocs": None,
            "software_ultimo": ["Google Chrome", "Word"],
            "config": None,
            "logo_path": "x",
            "generado": timezone.now(),
        })
        self.assertIn(self.activo.serial, html)
        self.assertIn("Historial de mantenimientos", html)
        self.assertIn("Limpieza general", html)
        self.assertIn("Cambio de parte", html)
        self.assertIn("Disco duro", html)
        self.assertIn("Teclado", html)
        self.assertIn("Mal", html)
        self.assertIn("Bien", html)
        self.assertIn("Google Chrome", html)
        self.assertIn("Antes del cambio", html)
        self.assertIn(foto.foto.path, html)


class ReporteActivosPdfTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo_con = Activo.objects.create(
            serial="SN-REP-001",
            tipo_dispositivo="escritorio",
            marca="HP",
            modelo="Pro",
            estado="disponible",
        )
        self.activo_sin = Activo.objects.create(
            serial="SN-REP-002",
            tipo_dispositivo="escritorio",
            marca="Dell",
            modelo="OptiPlex",
            estado="disponible",
        )

    def test_reporte_activos_pdf_returns_pdf(self):
        _orden(self.activo_con, estado="cerrada", fecha_cierre=HOY)
        with patch.dict("sys.modules", {"weasyprint": FakeWeasyPrintModule()}):
            resp = self.client.get(reverse("mantenimiento:reporte_activos_pdf"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_activos_con_ultimo_mantenimiento_solo_cerradas(self):
        from mantenimiento.services import _activos_con_ultimo_mantenimiento

        _orden(self.activo_con, estado="cerrada", fecha_cierre=HOY)
        _orden(self.activo_sin, estado="abierta")
        filas = _activos_con_ultimo_mantenimiento()
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["activo"].pk, self.activo_con.pk)
        self.assertEqual(filas[0]["ultima_cierre"], HOY)

    def test_reportes_toma_ultima_fecha_cierre(self):
        from mantenimiento.services import _activos_con_ultimo_mantenimiento

        _orden(self.activo_con, estado="cerrada", fecha_cierre=HOY - timedelta(days=5))
        _orden(self.activo_con, estado="cerrada", fecha_cierre=HOY)
        filas = _activos_con_ultimo_mantenimiento()
        self.assertEqual(filas[0]["ultima_cierre"], HOY)

    def test_reporte_activos_pdf_template_muestra_columnas(self):
        html = render_to_string("mantenimiento/reporte_activos_pdf.html", {
            "filas": [{"activo": self.activo_con, "ultima_cierre": HOY}],
            "config": None,
            "logo_path": "x",
            "generado": timezone.now(),
        })
        self.assertIn("SN-REP-001", html)
        self.assertIn("HP Pro", html)
        self.assertIn("Escritorio", html)
        self.assertIn(HOY.strftime("%d/%m/%Y"), html)
