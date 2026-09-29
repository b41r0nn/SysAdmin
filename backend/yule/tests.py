from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

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


class _FakeResponse:
    """Respuesta mínima para probar el parseo de OCS sin red."""

    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def json(self):
        import json

        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


class OCSClientGetComputersTests(TestCase):
    """OCS 2.12 quirks: con limit=0 /computers devuelve texto plano, no JSON."""

    def _client(self, body, status_code=200):
        from yule.client import OCSClient

        client = OCSClient(base_url="http://ocs/ocsapi/v1", user="u", token="t")
        client.request = lambda *a, **kw: _FakeResponse(body, status_code)
        return client

    def test_usa_limit_positivo_en_la_peticion(self):
        # limit=0 rompe contra OCS 2.12: devuelve "Argument..." en vez de JSON.
        client = self._client("null")
        capturadas = {}

        def fake_request(path, params=None, **kw):
            capturadas["path"] = path
            capturadas["params"] = params
            return _FakeResponse("null")

        client.request = fake_request
        client.get_computers()

        self.assertEqual(capturadas["path"], "computers")
        self.assertGreater(capturadas["params"]["limit"], 0)

    def test_null_de_ocs_devuelve_lista_vacia(self):
        self.assertEqual(self._client("null").get_computers(), [])

    def test_cuerpo_vacio_devuelve_lista_vacia(self):
        self.assertEqual(self._client("").get_computers(), [])

    def test_texto_plano_no_json_reporta_el_error_real(self):
        # Antes esto terminaba en "Failed to parse OCS response: Expecting
        # value: line 1 column 1 (char 0)", sin decir qué devolvió OCS.
        from yule.client import OCSClientException

        with self.assertRaises(OCSClientException) as ctx:
            self._client("Argument limit must be a positive integer").get_computers()

        self.assertIn("no es JSON", str(ctx.exception))
        self.assertIn("Argument limit", str(ctx.exception))

    def test_lista_de_computers_se_parsea(self):
        body = '[{"id": 42, "name": "PC-01"}]'
        self.assertEqual(self._client(body).get_computers(), [{"id": 42, "name": "PC-01"}])

    def test_dict_con_clave_computers_se_parsea(self):
        body = '{"computers": [{"id": 7, "name": "PC-07"}]}'
        self.assertEqual(self._client(body).get_computers(), [{"id": 7, "name": "PC-07"}])

    def test_dict_indexado_por_id_se_parsea(self):
        # Así responde OCS 2.12 en producción: {"1": {...}} y no una lista.
        body = '{"1": {"hardware": {"ID": 1, "NAME": "PC-01", "DEVICEID": "PC-01-2026-01-01-00-00-00"}}}'
        self.assertEqual(
            self._client(body).get_computers(),
            [{"id": "1", "hardware": {"ID": 1, "NAME": "PC-01", "DEVICEID": "PC-01-2026-01-01-00-00-00"}}],
        )

    def test_el_id_se_inyecta_desde_la_clave(self):
        # OCS 2.12 no manda el ID dentro del objeto, solo en la clave. Como
        # `id_ocs` es unique=True, sin esto todos los equipos colapsan en uno.
        equipos = self._client('{"7": {"NAME": "PC-07"}, "8": {"NAME": "PC-08"}}').get_computers()

        self.assertEqual([e["id"] for e in equipos], ["7", "8"])

    def test_el_id_existente_no_se_sobrescribe(self):
        equipos = self._client('{"7": {"id": 99, "NAME": "PC-07"}}').get_computers()

        self.assertEqual(equipos[0]["id"], 99)

    def test_software_desde_dict_indexado_por_id(self):
        from yule.client import OCSClient

        client = OCSClient(base_url="http://ocs/ocsapi/v1", user="u", token="t")
        client.request = lambda *a, **kw: _FakeResponse(
            '{"1": {"software": [{"NAME": "Chrome", "VERSION": "120.0"}]}}'
        )

        self.assertEqual(
            client.get_software("1"),
            [{"name": "Chrome", "version": "120.0", "publisher": ""}],
        )


class ExtractEquipoDataTests(TestCase):
    """El API de OCS devuelve las columnas de `hardware` en mayúsculas."""

    def test_lee_claves_en_mayusculas(self):
        from yule.sync import _extract_equipo_data

        datos = _extract_equipo_data(
            {
                "ID": 1,
                "NAME": "PC-01",
                "USER": "REDIHOS\\jperez",
                "HARDWARE": {
                    "OSNAME": "Windows 11 Pro",
                    "OSVERSION": "10.0.22631",
                    "MEMORY": 16384,
                    "PROCESSORS": {"NAME": "Intel(R) Core(TM) i5-10400"},
                },
                "BIOS": {"SN": "ABC123"},
                "NETWORKS": [{"MACADDR": "AA:BB:CC:DD:EE:FF", "IPADDRESS": "192.168.1.140"}],
            }
        )

        self.assertEqual(datos["id_ocs"], "1")
        self.assertEqual(datos["nombre_host"], "PC-01")
        self.assertEqual(datos["usuario_dominio"], "REDIHOS\\jperez")
        self.assertEqual(datos["so_nombre"], "Windows 11 Pro")
        self.assertEqual(datos["so_version"], "10.0.22631")
        self.assertEqual(datos["memoria_ram_mb"], 16384)
        self.assertEqual(datos["procesador"], "Intel(R) Core(TM) i5-10400")
        self.assertEqual(datos["serial_bios"], "ABC123")
        self.assertEqual(datos["mac_address"], "AA:BB:CC:DD:EE:FF")
        self.assertEqual(datos["ip_address"], "192.168.1.140")

    def test_lee_claves_en_minusculas(self):
        from yule.sync import _extract_equipo_data

        datos = _extract_equipo_data(
            {
                "id": 2,
                "name": "PC-02",
                "hardware": {"osname": "Linux", "memory": 8192},
                "bios": {"sn": "XYZ789"},
                "networks": [{"macaddr": "11:22:33:44:55:66"}],
            }
        )

        self.assertEqual(datos["id_ocs"], "2")
        self.assertEqual(datos["nombre_host"], "PC-02")
        self.assertEqual(datos["so_nombre"], "Linux")
        self.assertEqual(datos["serial_bios"], "XYZ789")

    def test_ultimo_reporte_toma_lastcome_de_ocs(self):
        # Antes ponía datetime.now(): la UI decía "reportó ahora" para un
        # equipo que nunca había reportado.
        from yule.sync import _extract_equipo_data

        datos = _extract_equipo_data(
            {"id": 3, "name": "PC-03", "hardware": {"LASTCOME": "2026-09-25 15:48:03"}}
        )

        self.assertIsNotNone(datos["ultimo_reporte_ocs"])
        self.assertEqual(datos["ultimo_reporte_ocs"].strftime("%Y-%m-%d %H:%M:%S"), "2026-09-25 15:48:03")
        self.assertTrue(timezone.is_aware(datos["ultimo_reporte_ocs"]))

    def test_sin_lastcome_queda_null(self):
        from yule.sync import _extract_equipo_data

        datos = _extract_equipo_data({"id": 4, "name": "PC-04", "hardware": {}})

        self.assertIsNone(datos["ultimo_reporte_ocs"])

    def test_sin_id_se_genera_clave_derivada_unica(self):
        # id_ocs es unique=True: dos equipos sin id no pueden terminar en el
        # mismo registro.
        from yule.sync import _extract_equipo_data

        a = _extract_equipo_data({"NAME": "PC-A", "NETWORKS": [{"MACADDR": "AA:AA:AA:AA:AA:AA"}]})
        b = _extract_equipo_data({"NAME": "PC-B", "NETWORKS": [{"MACADDR": "BB:BB:BB:BB:BB:BB"}]})

        self.assertTrue(a["id_ocs"])
        self.assertNotEqual(a["id_ocs"], b["id_ocs"])

    def test_nombre_vacio_no_muestra_unknown(self):
        from yule.sync import _extract_equipo_data

        datos = _extract_equipo_data({"id": 5, "hardware": {}})

        self.assertEqual(datos["nombre_host"], "(sin nombre)")

    def test_ip_se_toma_de_otra_interfaz_si_la_primera_no_tiene(self):
        # La primera interfaz suele ser la de management: MAC sí, IP no.
        from yule.sync import _extract_equipo_data

        datos = _extract_equipo_data(
            {
                "id": 6,
                "name": "PC-06",
                "networks": [
                    {"MACADDR": "00:09:0F:AA:00:01", "IPADDRESS": ""},
                    {"MACADDR": "A4:BB:6D:11:22:33", "IPADDRESS": "192.168.1.137"},
                ],
            }
        )

        self.assertEqual(datos["mac_address"], "00:09:0F:AA:00:01")
        self.assertEqual(datos["ip_address"], "192.168.1.137")

    def test_payload_real_ocs_212_se_mapea_completo(self):
        # Fixture tomado de `/ocsapi/v1/computers?limit=1` de OCS 2.12.1. En esa
        # forma `bios` es lista, `PROCESSORS` es un entero (MHz) y la primera
        # interfaz es virtual del firewall: con el parser anterior quedaban
        # serial, procesador, IP y MAC vacíos o equivocados.
        from yule.sync import _extract_equipo_data

        datos = _extract_equipo_data(
            {
                "accountinfo": {"ID": 3},
                "bios": [
                    {
                        "HARDWARE_ID": 3,
                        "SSN": "F35F284",
                        "MSN": "/F35F284/VNWSV0051K0C5N/",
                        "SMODEL": "Latitude 3450",
                    }
                ],
                "cpus": [{"TYPE": "13th Gen Intel(R) Core(TM) i5-1335U", "MANUFACTURER": "GenuineIntel"}],
                "hardware": {
                    "ID": 3,
                    "NAME": "W11F35F",
                    "IPADDR": "192.168.1.137",
                    "USERID": "Sistemas",
                    "USERDOMAIN": None,
                    "WORKGROUP": "redihossas.local",
                    "LASTCOME": "2026-09-28 20:27:57",
                    "MEMORY": 16288,
                    "OSNAME": "Microsoft Windows 11 Pro",
                    "OSVERSION": "10.0.26200",
                    "PROCESSORT": "13th Gen Intel(R) Core(TM) i5-1335U [10 core(s) x86_64]",
                    "PROCESSORS": 1300,
                },
                "networks": [
                    {
                        "MACADDR": "00:09:0F:AA:00:01",
                        "IPADDRESS": "",
                        "STATUS": "",
                        "TYPE": "Ethernet",
                    },
                    {
                        "MACADDR": "E8:CF:83:0A:8C:0E",
                        "IPADDRESS": "192.168.1.137",
                        "STATUS": "Up",
                        "TYPE": "Ethernet",
                    },
                ],
                "storages": [{"TYPE": "Disk", "DISKSIZE": 488382}],
            }
        )

        self.assertEqual(datos["id_ocs"], "3")
        self.assertEqual(datos["nombre_host"], "W11F35F")
        self.assertEqual(datos["usuario_dominio"], "redihossas.local\\Sistemas")
        self.assertEqual(datos["serial_bios"], "F35F284")
        self.assertEqual(datos["procesador"], "13th Gen Intel(R) Core(TM) i5-1335U [10 core(s) x86_64]")
        self.assertEqual(datos["ip_address"], "192.168.1.137")
        # MAC de la interfaz que tiene la IP real, no la virtual del firewall.
        self.assertEqual(datos["mac_address"], "E8:CF:83:0A:8C:0E")
        self.assertEqual(datos["memoria_ram_mb"], 16288)
        # El campo del modelo es PositiveIntegerField: el helper devuelve int.
        # 488382 MB / 1024 = 476.94 -> 477. Antes devolvía 476.9 y Django lo
        # truncaba a 476 al guardar.
        self.assertIsInstance(datos["almacenamiento_total_gb"], int)
        self.assertEqual(datos["almacenamiento_total_gb"], 477)
        self.assertEqual(
            datos["ultimo_reporte_ocs"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "2026-09-28 20:27:57",
        )

    def test_lastcome_se_interpreta_como_utc(self):
        # OCS lo escribe con NOW() de la BD (UTC): el access log marcaba
        # 22:27:57 +0200 y LASTCOME traía 20:27:57. Leerlo como hora local
        # (America/Bogota) corría el reporte 5 horas.
        from yule.sync import _extract_equipo_data

        datos = _extract_equipo_data(
            {"id": 7, "name": "PC-07", "hardware": {"LASTCOME": "2026-09-28 20:27:57"}}
        )

        self.assertEqual(datos["ultimo_reporte_ocs"].utcoffset().total_seconds(), 0)
        self.assertEqual(
            datos["ultimo_reporte_ocs"].strftime("%Y-%m-%d %H:%M:%S"), "2026-09-28 20:27:57"
        )

    def test_procesador_usa_cpus_si_no_hay_processort(self):
        from yule.sync import _extract_equipo_data

        datos = _extract_equipo_data(
            {
                "id": 8,
                "name": "PC-08",
                "hardware": {"PROCESSORS": 1300},
                "cpus": [{"TYPE": "AMD Ryzen 5 7530U"}],
            }
        )

        self.assertEqual(datos["procesador"], "AMD Ryzen 5 7530U")

    def test_software_se_lee_de_la_seccion_con_clave_vacia(self):
        # `/computer/{id}` devuelve {"3": {"": [{NAME, VERSION, ...}]}}: la
        # sección de software llega con la clave literal vacía.
        from yule.client import OCSClient

        rows = OCSClient._find_software_rows(
            {
                "3": {
                    "": [
                        {"NAME": "Google Chrome", "VERSION": "140.0", "PUBLISHER": "Google LLC"},
                        {"NAME": "Notepad++", "VERSION": "8.7", "PUBLISHER": "Don Ho"},
                    ]
                }
            }
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["NAME"], "Google Chrome")

    def test_software_no_confunde_otras_listas_de_la_respuesta(self):
        # `memories`, `monitors`... también son listas; solo cuentan si traen
        # nombre y versión.
        from yule.client import OCSClient

        self.assertEqual(
            OCSClient._find_software_rows({"3": {"memories": [{"CAPACITY": 16288}]}}),
            [],
        )

    def test_software_solo_toma_la_seccion_software_del_payload_real(self):
        # Reproduce la forma REAL de `/computer/3` en OCS 2.12: el software
        # aparece dos veces (clave "" con nombres resueltos y clave "software"
        # con NAME_ID) y alrededor hay 17 secciones más. Varias de esas
        # secciones (printers, slots, ports) también traen clave "name", así
        # que acumular todas las listas las mezclaba en el inventario: se
        # devolvían 157 entradas en vez de 122.
        from yule.client import OCSClient

        software_resuelto = [
            {"NAME": "Google Chrome", "VERSION": "153.0.8010.54", "PUBLISHER": "Google LLC"},
            {"NAME": "AnyDesk", "VERSION": "ad 9.0.14", "PUBLISHER": "AnyDesk Software GmbH"},
        ]
        software_por_id = [
            {"NAME_ID": 1, "VERSION_ID": 2, "PUBLISHER_ID": 3, "HARDWARE_ID": 3},
        ]
        payload = {
            "3": {
                "": software_resuelto,
                "software": software_por_id,
                "networks": [{"MACADDR": "E8:CF:83:0A:8C:0E", "IPADDRESS": "192.168.1.137"}],
                "printers": [{"NAME": "Dell Optimizer", "VERSION": "1.0", "DRIVER": "x"}],
                "slots": [{"NAME": "Ranura de sistema", "TYPE": "PCI"}],
                "ports": [{"NAME": "USB Root Hub", "TYPE": "USB"}],
                "sounds": [{"NAME": "Realtek Audio", "VERSION": "6.0.1.1"}],
                "controllers": [{"NAME": "Kaspersky", "VERSION": "15.1.0.11795"}],
                "inputs": [{"NAME": "HID Keyboard", "TYPE": "Keyboard"}],
                "monitors": [{"NAME": "Monitor P2419", "SERIAL": "x"}],
                "memories": [{"CAPACITY": 16288, "SERIALNUMBER": "x"}],
                "accountinfo": [{"NAME": "sistemas"}],
                "bios": [{"SSN": "F35F284", "SMODEL": "Latitude 3450"}],
                "cpus": [{"TYPE": "13th Gen Intel(R) Core(TM) i5-1335U"}],
                "storages": [{"TYPE": "Disk", "DISKSIZE": 488382}],
                "hardware": {"ID": 3, "NAME": "W11F35F"},
            }
        }

        filas = OCSClient._find_software_rows(payload)

        # Solo la sección de software, con los nombres ya resueltos.
        self.assertEqual(len(filas), 2)
        self.assertEqual([f["NAME"] for f in filas], ["Google Chrome", "AnyDesk"])
        # Y desde luego nada de las otras 16 secciones.
        ajenos = {"Dell Optimizer", "Ranura de sistema", "USB Root Hub",
                   "Realtek Audio", "Kaspersky", "HID Keyboard", "Monitor P2419"}
        self.assertEqual(ajenos & {f.get("NAME") for f in filas}, set())

    def test_get_software_descarta_filas_sin_nombre(self):
        # La sección "software" con NAME_ID no trae nombre: si se usara esa,
        # el inventario quedaría con entradas vacías.
        from yule.client import OCSClient

        filas = OCSClient._find_software_rows(
            {"7": {"software": [{"NAME_ID": 1, "VERSION_ID": 2}]}}
        )
        self.assertEqual(filas, [])


def _activo(**kw):
    from inventario.models import Activo

    defaults = {
        "serial": f"SN-MATCH-{Activo.objects.count() + 1}",
        "tipo_dispositivo": "portatil",
        "marca": "Dell",
        "modelo": "Latitude 3450",
    }
    defaults.update(kw)
    return Activo.objects.create(**defaults)


class YuleMatchingTests(TestCase):
    """Cobertura de `buscar_posibles_matches`.

    Los tres casos que fallaban en producción venían de la misma raíz: el
    inventario y OCS no escriben los mismos identificadores en el mismo sitio.
    """

    def _motivos(self, equipo, activo):
        from yule.sync import buscar_posibles_matches

        for candidato, motivos in buscar_posibles_matches(equipo):
            if candidato.pk == activo.pk:
                return motivos
        return []

    def test_serial_identico(self):
        eq = _equipo(serial_bios="F35F284")
        activo = _activo(serial="F35F284")
        self.assertIn("serial del BIOS idéntico", self._motivos(eq, activo))

    def test_serial_sin_distinguir_mayusculas(self):
        eq = _equipo(serial_bios="f35f284")
        activo = _activo(serial="F35F284")
        self.assertIn("serial del BIOS idéntico", self._motivos(eq, activo))

    def test_mac_con_guiones_contra_ocs_con_dos_puntos(self):
        # El inventario guarda guiones y OCS devuelve dos puntos: un icontains
        # entre los dos formatos nunca coincidía, así que la MAC era un campo
        # muerto para el matching.
        eq = _equipo(mac_address="E8:CF:83:0A:8C:0E")
        activo = _activo(mac_equipo="E8-CF-83-0A-8C-0E")
        self.assertIn("misma MAC de red", self._motivos(eq, activo))

    def test_mac_no_coincide_si_es_otra(self):
        eq = _equipo(mac_address="E8:CF:83:0A:8C:0E")
        activo = _activo(mac_equipo="00:11:22:33:44:55")
        self.assertEqual(self._motivos(eq, activo), [])

    def test_hostname_contra_nombre_equipo(self):
        # Antes la búsqueda por hostname miraba `observaciones`, un campo donde
        # nadie escribe el nombre del equipo: por eso salía vacía.
        eq = _equipo(nombre_host="W11F35F")
        activo = _activo(nombre_equipo="W11F35F")
        self.assertIn("mismo nombre de equipo", self._motivos(eq, activo))

    def test_hostname_guardado_en_el_serial(self):
        # Caso real del activo 24: el hostname se había capturado en el campo del
        # service tag en lugar del nombre de equipo.
        eq = _equipo(nombre_host="W11F35F")
        activo = _activo(serial="W11F35F", nombre_equipo="")
        self.assertIn("el hostname está en el campo serial del activo", self._motivos(eq, activo))

    def test_no_propone_activos_ya_ocupados_por_otro_equipo(self):
        # Un activo con dos equipos OCS hace que snapshot_software_ocs() tenga
        # que elegir con .first(), así que no debe ofrecerse como candidato.
        eq = _equipo(nombre_host="W11F35F")
        otro = _equipo(id_ocs="OTRO-1", nombre_host="otro-host")
        activo = _activo(nombre_equipo="W11F35F")
        otro.activo_local = activo
        otro.save()
        self.assertEqual(self._motivos(eq, activo), [])

    def test_ordena_el_candidato_con_mas_motivos_primero(self):
        eq = _equipo(nombre_host="W11F35F", serial_bios="F35F284")
        debil = _activo(serial="F35F284")
        fuerte = _activo(serial="F35F2842", nombre_equipo="W11F35F")
        from yule.sync import buscar_posibles_matches

        orden = [a.pk for a, _ in buscar_posibles_matches(eq)]
        self.assertEqual(orden[0], fuerte.pk)
        self.assertIn(debil.pk, orden)

    def test_serial_similar_no_es_el_mismo_activo(self):
        # F35284 y F95F284 se parecen a F35F284 pero son Latitude 3440: el
        # parecido no debe convertirse en una propuesta de vinculación.
        eq = _equipo(serial_bios="F35F284")
        otro = _activo(serial="F35284", modelo="Latitude 3440")
        self.assertEqual(self._motivos(eq, otro), [])

    def test_sin_identificadores_no_revienta(self):
        eq = _equipo(serial_bios="", mac_address="", nombre_host="")
        from yule.sync import buscar_posibles_matches

        self.assertEqual(buscar_posibles_matches(eq), [])


class YuleVinculacionTests(TestCase):
    """La vinculación tiene que poder hacerse desde la app, no solo en el admin."""

    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_vincular_activo_por_post(self):
        eq = _equipo(nombre_host="W11F35F", serial_bios="F35F284")
        activo = _activo(serial="F35F284")

        resp = self.client.post(
            reverse("yule:vincular_activo", args=[eq.pk]), {"activo": activo.pk}
        )

        self.assertEqual(resp.status_code, 302)
        eq.refresh_from_db()
        self.assertEqual(eq.activo_local_id, activo.pk)

    def test_vincular_redirige_al_detalle(self):
        eq = _equipo()
        activo = _activo()
        resp = self.client.post(
            reverse("yule:vincular_activo", args=[eq.pk]), {"activo": activo.pk}
        )
        self.assertEqual(resp.url, reverse("yule:equipo_detalle", args=[eq.pk]))

    def test_no_se_puede_vincular_dos_equipos_al_mismo_activo(self):
        eq = _equipo(id_ocs="A-1")
        otro = _equipo(id_ocs="B-2")
        activo = _activo()
        otro.activo_local = activo
        otro.save()

        resp = self.client.post(
            reverse("yule:vincular_activo", args=[eq.pk]), {"activo": activo.pk}
        )

        eq.refresh_from_db()
        self.assertIsNone(eq.activo_local_id)
        textos = [str(m) for m in resp.wsgi_request._messages]
        self.assertTrue(any("ya está vinculado" in t for t in textos), textos)

    def test_revincular_requiere_desvincular_primero(self):
        eq = _equipo(id_ocs="A-1")
        primero = _activo(serial="SN-UNO")
        segundo = _activo(serial="SN-DOS")
        eq.activo_local = primero
        eq.save()

        self.client.post(
            reverse("yule:vincular_activo", args=[eq.pk]), {"activo": segundo.pk}
        )

        eq.refresh_from_db()
        self.assertEqual(eq.activo_local_id, primero.pk)

    def test_desvincular(self):
        eq = _equipo()
        activo = _activo()
        eq.activo_local = activo
        eq.save()

        resp = self.client.post(reverse("yule:desvincular_activo", args=[eq.pk]))

        self.assertEqual(resp.status_code, 302)
        eq.refresh_from_db()
        self.assertIsNone(eq.activo_local_id)

    def test_vincular_exige_post(self):
        eq = _equipo()
        activo = _activo()
        resp = self.client.get(reverse("yule:vincular_activo", args=[eq.pk]))
        self.assertEqual(resp.status_code, 405)
        eq.refresh_from_db()
        self.assertIsNone(eq.activo_local_id)

    def test_lectura_no_puede_vincular(self):
        self.client.force_login(_user("lectura"))
        eq = _equipo()
        activo = _activo()
        resp = self.client.post(
            reverse("yule:vincular_activo", args=[eq.pk]), {"activo": activo.pk}
        )
        self.assertEqual(resp.status_code, 302)
        eq.refresh_from_db()
        self.assertIsNone(eq.activo_local_id)

    def test_api_buscar_activos(self):
        _activo(serial="F35F284", marca="Dell", modelo="Latitude 3450")
        resp = self.client.get(reverse("yule:api_buscar_activos"), {"q": "F35"})
        self.assertEqual(resp.status_code, 200)
        datos = resp.json()["resultados"]
        self.assertEqual(len(datos), 1)
        self.assertEqual(datos[0]["serial"], "F35F284")

    def test_api_buscar_activos_con_texto_no_devuelve_500(self):
        # numero_interno es un entero: filtrar por él con texto lanzaba ValueError.
        _activo(serial="F35F284", marca="Dell")
        resp = self.client.get(reverse("yule:api_buscar_activos"), {"q": "Dell"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["resultados"])

    def test_api_buscar_activos_exige_dos_caracteres(self):
        resp = self.client.get(reverse("yule:api_buscar_activos"), {"q": "F"})
        self.assertEqual(resp.json()["resultados"], [])

    def test_api_buscar_activos_marca_ocupados(self):
        eq = _equipo()
        activo = _activo(serial="OCUPADO-1")
        eq.activo_local = activo
        eq.save()
        resp = self.client.get(reverse("yule:api_buscar_activos"), {"q": "OCUPADO"})
        self.assertTrue(resp.json()["resultados"][0]["ocupado"])

    def test_el_detalle_muestra_el_panel_de_vinculacion(self):
        eq = _equipo(nombre_host="W11F35F", serial_bios="F35F284")
        _activo(serial="F35F284")
        resp = self.client.get(reverse("yule:equipo_detalle", args=[eq.pk]))
        # reverse() resuelve a la ruta, así que en el HTML aparece "/vincular/".
        self.assertContains(resp, reverse("yule:vincular_activo", args=[eq.pk]))
        self.assertContains(resp, "serial del BIOS idéntico")

    def test_el_detalle_no_ofrece_panel_si_ya_esta_vinculado(self):
        eq = _equipo()
        activo = _activo()
        eq.activo_local = activo
        eq.save()
        resp = self.client.get(reverse("yule:equipo_detalle", args=[eq.pk]))
        self.assertNotContains(resp, reverse("yule:vincular_activo", args=[eq.pk]))
        self.assertContains(resp, reverse("yule:desvincular_activo", args=[eq.pk]))

    def test_la_lista_sin_match_ofrece_la_vinculacion(self):
        eq = _equipo(nombre_host="W11F35F", serial_bios="F35F284")
        _activo(serial="F35F284")
        resp = self.client.get(reverse("yule:equipos_sin_match"))
        self.assertContains(resp, reverse("yule:vincular_activo", args=[eq.pk]))

