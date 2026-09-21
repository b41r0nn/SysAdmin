from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from yule.client import build_client
from yule.forms import ConfiguracionYuleForm
from yule.models import ConfiguracionYule, EquipoOCS, SincronizacionLog
from yule.sync import sincronizar_equipos_ocs

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


class YuleFormTests(TestCase):
    def test_guardar_cifra_password(self):
        form = ConfiguracionYuleForm(data={
            "url": "https://srv.ocs.redihos.local:8080/ocsapi/v1/",
            "usuario": "ocs_user",
            "ocs_password": "supersecreto",
            "frecuencia_sync_minutos": 60,
        })
        self.assertTrue(form.is_valid(), form.errors)
        inst = form.save()
        self.assertNotEqual(inst.password_cifrada, "supersecreto")
        self.assertNotIn("supersecreto", inst.password_cifrada)
        self.assertEqual(inst.get_ocs_password(), "supersecreto")

    def test_email_en_blanco_conserva_password(self):
        config = ConfiguracionYule.objects.create(
            nombre="Configuración OCS",
            activa=True,
            url="https://srv.ocs.redihos.local:8080/ocsapi/v1",
            usuario="ocs_user",
        )
        config.set_ocs_password("pass-anterior")
        config.save()

        form = ConfiguracionYuleForm(data={
            "url": "https://srv.ocs.redihos.local:8080/ocsapi/v1/nuevo",
            "usuario": "ocs_user",
            "ocs_password": "",
            "frecuencia_sync_minutos": 60,
        }, instance=config)
        self.assertTrue(form.is_valid(), form.errors)
        inst = form.save()

        inst.refresh_from_db()
        self.assertEqual(inst.url.rstrip("/"), "https://srv.ocs.redihos.local:8080/ocsapi/v1/nuevo")
        self.assertEqual(inst.get_ocs_password(), "pass-anterior")

    def test_clean_url_quita_slash_final(self):
        form = ConfiguracionYuleForm(data={
            "url": "https://srv.ocs.redihos.local:8443/ocsapi/v1///",
            "usuario": "u",
            "frecuencia_sync_minutos": 60,
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["url"], "https://srv.ocs.redihos.local:8443/ocsapi/v1")

    def test_cambio_password_actualiza(self):
        config = ConfiguracionYule.objects.create(
            nombre="Configuración OCS",
            activa=True,
            url="https://srv.ocs.redihos.local:8080/ocsapi/v1",
            usuario="ocs_user",
        )
        config.set_ocs_password("viejo")
        config.save()

        form = ConfiguracionYuleForm(data={
            "url": "https://srv.ocs.redihos.local:8080/ocsapi/v1",
            "usuario": "ocs_user",
            "ocs_password": "nuevo",
            "frecuencia_sync_minutos": 60,
        }, instance=config)
        self.assertTrue(form.is_valid(), form.errors)
        inst = form.save()
        inst.refresh_from_db()
        self.assertEqual(inst.get_ocs_password(), "nuevo")


class YuleBuildClientTests(TestCase):
    @override_settings(OCS_BASE_URL="https://fallback.host:8443/ocsapi/v1",
                       OCS_USER="fb_user", OCS_TOKEN="fb_token")
    def test_sin_fila_fallback_a_settings(self):
        client = build_client()
        self.assertTrue(client.is_configured())
        self.assertEqual(client.base_url, "https://fallback.host:8443/ocsapi/v1")
        self.assertEqual(client.user, "fb_user")
        self.assertEqual(client.token, "fb_token")

    def test_fila_bd_activa_usa_datos_bd(self):
        config = ConfiguracionYule.objects.create(
            nombre="Configuración OCS",
            activa=True,
            integracion_activa=True,
            url="https://srv.ocs.redihos.local:8080/ocsapi/v1",
            usuario="ocs_user",
        )
        config.set_ocs_password("token-bd")
        config.save()

        client = build_client()
        self.assertTrue(client.is_configured())
        self.assertEqual(client.base_url, "https://srv.ocs.redihos.local:8080/ocsapi/v1")
        self.assertEqual(client.user, "ocs_user")
        self.assertEqual(client.token, "token-bd")

    @override_settings(OCS_BASE_URL="https://fallback.host:8443/ocsapi/v1",
                       OCS_USER="fb_user", OCS_TOKEN="fb_token")
    def test_fila_inactiva_devuelve_cliente_no_configurado(self):
        ConfiguracionYule.objects.create(
            nombre="Configuración OCS",
            activa=True,
            integracion_activa=False,
            url="https://srv.ocs.redihos.local:8080/ocsapi/v1",
            usuario="ocs_user",
        )
        client = build_client()
        self.assertFalse(client.is_configured())

    @override_settings(OCS_BASE_URL="https://fallback.host:8443/ocsapi/v1",
                       OCS_USER="fb_user", OCS_TOKEN="fb_token")
    def test_fila_sin_url_usuario_fallback_a_settings(self):
        ConfiguracionYule.objects.create(
            nombre="Configuración OCS",
            activa=True,
            integracion_activa=True,
            url="",
            usuario="",
        )
        client = build_client()
        self.assertTrue(client.is_configured())
        self.assertEqual(client.base_url, "https://fallback.host:8443/ocsapi/v1")
        self.assertEqual(client.user, "fb_user")
        self.assertEqual(client.token, "fb_token")


class YuleSyncTests(TestCase):
    @override_settings(OCS_BASE_URL="", OCS_USER="", OCS_TOKEN="")
    def test_sync_cliente_no_configurado_no_lanza_parcial(self):
        # Sin fila en BD y sin settings → cliente no configurado
        client = build_client()
        self.assertFalse(client.is_configured())

        log, msg = sincronizar_equipos_ocs()

        self.assertEqual(log.estado, "parcial")
        self.assertIn("No se sincronizó", msg)
        self.assertIsNotNone(log.fecha_fin)
        self.assertGreaterEqual(log.duracion_segundos, 0)

    @override_settings(OCS_BASE_URL="", OCS_USER="", OCS_TOKEN="")
    def test_sync_integracion_desactivada_no_lanza(self):
        ConfiguracionYule.objects.create(
            nombre="Configuración OCS",
            activa=True,
            integracion_activa=False,
            url="https://srv.ocs.redihos.local:8080/ocsapi/v1",
            usuario="ocs_user",
        )
        log, msg = sincronizar_equipos_ocs()

        self.assertEqual(log.estado, "parcial")
        self.assertIn("No se sincronizó", msg)
