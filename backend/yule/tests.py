from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from yule.models import ConfiguracionYule, EquipoOCS, SincronizacionLog

CustomUser = get_user_model()


def _user(rol):
    return CustomUser.objects.create_user(
        username=f"yule_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


def _equipo(**kw):
    defaults = {
        "id_ocs": f"OCS-{EquipoOCS.objects.count() + 1}",
        "nombre_host": "host-local",
    }
    defaults.update(kw)
    return EquipoOCS.objects.create(**defaults)


class YuleLoginTests(TestCase):
    def test_index_requiere_login(self):
        resp = self.client.get(reverse("yule:index"))
        self.assertEqual(resp.status_code, 302)

    def test_equipos_requiere_login(self):
        resp = self.client.get(reverse("yule:equipos_lista"))
        self.assertEqual(resp.status_code, 302)


class YuleDashboardTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_index_returns_200(self):
        resp = self.client.get(reverse("yule:index"))
        self.assertEqual(resp.status_code, 200)

    def test_equipos_lista_returns_200(self):
        resp = self.client.get(reverse("yule:equipos_lista"))
        self.assertEqual(resp.status_code, 200)

    def test_equipos_sin_match_returns_200(self):
        _equipo()
        resp = self.client.get(reverse("yule:equipos_sin_match"))
        self.assertEqual(resp.status_code, 200)

    def test_historial_returns_200(self):
        resp = self.client.get(reverse("yule:historial"))
        self.assertEqual(resp.status_code, 200)

    def test_detalle_equipo(self):
        eq = _equipo()
        resp = self.client.get(reverse("yule:equipo_detalle", args=[eq.pk]))
        self.assertEqual(resp.status_code, 200)


class YuleModelTests(TestCase):
    def test_equipo_o_str(self):
        eq = _equipo(nombre_host="PC-001")
        self.assertIn("PC-001", str(eq))

    def test_configuracion_str(self):
        cfg = ConfiguracionYule.objects.create()
        self.assertIn("Configuración", str(cfg))

    def test_equipo_vinculado(self):
        from inventario.models import Activo

        activo = Activo.objects.create(
            serial="SN-YULE-001",
            tipo_dispositivo="escritorio",
            marca="Dell",
            modelo="OptiPlex",
        )
        eq = _equipo(activo_local=activo)
        self.assertIsNotNone(eq.activo_local)

    def test_equipo_sin_vincular(self):
        eq = _equipo()
        self.assertIsNone(eq.activo_local)


class YulePermisosTests(TestCase):
    def test_lectura_puede_ver_lista(self):
        user = _user("lectura")
        self.client.force_login(user)
        resp = self.client.get(reverse("yule:equipos_lista"))
        self.assertEqual(resp.status_code, 200)
