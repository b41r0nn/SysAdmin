from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventario.models import Activo
from mantenimiento.forms import ReporteFallaForm
from mantenimiento.models import ChecklistItem, OrdenMantenimiento, PlanMantenimiento, Repuesto
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


def _plan(activo, **kw):
    defaults = {"tipo": "preventivo", "estado": "activo"}
    defaults.update(kw)
    return PlanMantenimiento.objects.create(activo=activo, **defaults)


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
        p = _plan(self.activo)
        resp = self.client.get(reverse("mantenimiento:detalle_plan", args=[p.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_crear_plan_post(self):
        resp = self.client.post(
            reverse("mantenimiento:crear_plan"),
            {
                "activo": self.activo.pk,
                "tipo": "preventivo",
                "criticidad": "alta",
                "frecuencia_dias": 30,
                "estado": "activo",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(PlanMantenimiento.objects.filter(activo=self.activo).exists())

    def test_toggle_plan(self):
        p = _plan(self.activo, estado="activo")
        resp = self.client.post(reverse("mantenimiento:toggle_plan", args=[p.pk]))
        self.assertEqual(resp.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.estado, "pausado")

    def test_eliminar_plan_sin_ordenes(self):
        p = _plan(self.activo)
        resp = self.client.post(reverse("mantenimiento:eliminar_plan", args=[p.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PlanMantenimiento.objects.filter(pk=p.pk).exists())

    def test_eliminar_plan_con_ordenes_fallido(self):
        p = _plan(self.activo)
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
        plan = _plan(self.activo)
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
        plan = _plan(self.activo, proxima_ejecucion=HOY + timedelta(days=3))

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
        plan = _plan(self.activo, tipo="preventivo", proxima_ejecucion=HOY + timedelta(days=5))
        resp = self.client.get(reverse("mantenimiento:calendario_eventos"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        titulos = [e["title"] for e in data]
        self.assertTrue(any(f"Orden #{orden.id}" in t for t in titulos))
        self.assertTrue(any(f"Plan Preventivo" in t for t in titulos))
