from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventario.models import Activo
from prestamos.models import Prestamo

CustomUser = get_user_model()


def _user(rol):
    return CustomUser.objects.create_user(
        username=f"pres_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


def _activo(serial="SN-PRES-001"):
    return Activo.objects.create(
        serial=serial,
        tipo_dispositivo="portatil",
        marca="Lenovo",
        modelo="ThinkPad",
        estado="disponible",
    )


def _prestamo(activo, solicitante, **kw):
    defaults = {"fecha_prestamo": date.today() - timedelta(days=5)}
    defaults.update(kw)
    return Prestamo.objects.create(activo=activo, solicitante=solicitante, **defaults)


# ─── Acceso ────────────────────────────────────────────────────────


class PrestamosLoginTests(TestCase):
    def test_lista_requiere_login(self):
        resp = self.client.get(reverse("prestamos:lista"))
        self.assertEqual(resp.status_code, 302)

    def test_crear_requiere_login(self):
        resp = self.client.get(reverse("prestamos:crear"))
        self.assertEqual(resp.status_code, 302)


# ─── CRUD ──────────────────────────────────────────────────────────


class PrestamosCRUDTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_lista_returns_200(self):
        _prestamo(self.activo, self.user)
        resp = self.client.get(reverse("prestamos:lista"))
        self.assertEqual(resp.status_code, 200)

    def test_crear_prestamo_post(self):
        resp = self.client.post(
            reverse("prestamos:crear"),
            {
                "activo": self.activo.pk,
                "solicitante": self.user.pk,
                "fecha_prestamo": date.today() - timedelta(days=5),
                "fecha_devolucion_prevista": date.today() + timedelta(days=10),
                "destino": "Feria de tecnología",
            },
        )
        self.assertEqual(resp.status_code, 302)
        prestamo = Prestamo.objects.get(activo=self.activo)
        self.assertEqual(prestamo.solicitante, self.user)
        self.assertEqual(prestamo.estado, "activo")

    def test_crear_rechaza_prestamo_vigente(self):
        _prestamo(self.activo, self.user)
        resp = self.client.post(
            reverse("prestamos:crear"),
            {
                "activo": self.activo.pk,
                "solicitante": self.user.pk,
                "fecha_prestamo": "2026-09-01",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Prestamo.objects.count(), 1)

    def test_editar_prestamo(self):
        prestamo = _prestamo(self.activo, self.user)
        resp = self.client.post(
            reverse("prestamos:editar", args=[prestamo.pk]),
            {
                "activo": self.activo.pk,
                "solicitante": self.user.pk,
                "fecha_prestamo": "2026-09-01",
                "destino": "Actualizado",
            },
        )
        self.assertEqual(resp.status_code, 302)
        prestamo.refresh_from_db()
        self.assertEqual(prestamo.destino, "Actualizado")

    def test_detalle_returns_200(self):
        prestamo = _prestamo(self.activo, self.user)
        resp = self.client.get(reverse("prestamos:detalle", args=[prestamo.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_registrar_devolucion(self):
        prestamo = _prestamo(self.activo, self.user)
        resp = self.client.post(reverse("prestamos:devolver", args=[prestamo.pk]))
        self.assertEqual(resp.status_code, 302)
        prestamo.refresh_from_db()
        self.assertEqual(prestamo.estado, "devuelto")
        self.assertIsNotNone(prestamo.fecha_devolucion)


# ─── Estados ───────────────────────────────────────────────────────


class EstadoPrestamoTests(TestCase):
    def test_activo_sin_prevista(self):
        prestamo = _prestamo(_activo("SN-E1"), _user("tecnico"))
        self.assertEqual(prestamo.estado, "activo")

    def test_devuelto_primero(self):
        prestamo = _prestamo(
            _activo("SN-E2"),
            _user("tecnico"),
            fecha_devolucion_prevista=date.today() - timedelta(days=3),
            fecha_devolucion=date.today(),
        )
        self.assertEqual(prestamo.estado, "devuelto")

    def test_vencido_si_prevista_pasada(self):
        prestamo = _prestamo(
            _activo("SN-E3"),
            _user("tecnico"),
            fecha_devolucion_prevista=date.today() - timedelta(days=2),
        )
        self.assertEqual(prestamo.estado, "vencido")
        self.assertEqual(prestamo.dias_retraso(), 2)

    def test_filtro_por_estado_en_lista(self):
        activo_ok = _activo("SN-E4")
        _prestamo(activo_ok, _user("tecnico"))
        activo_vencido = _activo("SN-E5")
        _prestamo(
            activo_vencido,
            _user("tecnico"),
            fecha_devolucion_prevista=date.today() - timedelta(days=2),
        )

        user = _user("superadmin")
        self.client = Client()
        self.client.force_login(user)

        resp = self.client.get(reverse("prestamos:lista"), {"estado": "vencido"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, activo_vencido.serial)
        self.assertNotContains(resp, activo_ok.serial)


# ─── Permisos por rol ──────────────────────────────────────────────


class PrestamosPermisosTests(TestCase):
    def setUp(self):
        self.user = _user("lectura")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()
        self.prestamo = _prestamo(self.activo, self.user)

    def test_lectura_puede_ver_lista(self):
        resp = self.client.get(reverse("prestamos:lista"))
        self.assertEqual(resp.status_code, 200)

    def test_lectura_no_puede_crear(self):
        resp = self.client.get(reverse("prestamos:crear"))
        self.assertEqual(resp.status_code, 302)

    def test_lectura_no_puede_devolver(self):
        resp = self.client.post(reverse("prestamos:devolver", args=[self.prestamo.pk]))
        self.assertEqual(resp.status_code, 302)
        self.prestamo.refresh_from_db()
        self.assertEqual(self.prestamo.estado, "activo")

    def test_tecnico_puede_crear(self):
        tecnico = _user("tecnico")
        self.client.force_login(tecnico)
        otro_activo = _activo("SN-PRES-TEC")
        resp = self.client.post(
            reverse("prestamos:crear"),
            {
                "activo": otro_activo.pk,
                "solicitante": self.user.pk,
                "fecha_prestamo": "2026-09-01",
            },
        )
        self.assertEqual(resp.status_code, 302)
        prestamo = Prestamo.objects.get(activo=otro_activo)
        self.assertEqual(prestamo.solicitante, self.user)