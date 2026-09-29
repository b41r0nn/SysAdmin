from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from inventario.models import Activo, SoftwareInstalado
from inventario.views import _etiqueta_context
from usuarios.models import Usuario

CustomUser = get_user_model()


class FakeWeasyHTML:
    def __init__(self, *args, **kwargs):
        pass

    def write_pdf(self):
        return b"%PDF-1.4 fake-etiqueta"


class FakeWeasyPrintModule:
    HTML = FakeWeasyHTML


PDF_MODULE = FakeWeasyPrintModule()


def crear_usuario(rol):
    return CustomUser.objects.create_user(
        username=f"qr_{rol}_{CustomUser.objects.count()}",
        password="testpass123",
        rol=rol,
    )


def crear_activo(serial, **kwargs):
    defaults = {
        "tipo_dispositivo": "escritorio",
        "marca": "HP",
        "modelo": "EliteDesk",
        "estado": "disponible",
    }
    defaults.update(kwargs)
    return Activo.objects.create(serial=serial, **defaults)


class EtiquetasQRBase(TestCase):
    def setUp(self):
        self.usuario = crear_usuario("superadmin")
        self.activo = crear_activo("SN-TEST-001", nombre_equipo="PC-01")
        self.client.force_login(self.usuario)

    def _enter_pdf(self):
        return patch.dict("sys.modules", {"weasyprint": PDF_MODULE})


class QrImagenTests(EtiquetasQRBase):
    def test_no_autenticado_redirige_a_login(self):
        self.client.logout()
        response = self.client.get(reverse("inventario:qr_imagen", args=[self.activo.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_devuelve_png_del_activo(self):
        response = self.client.get(reverse("inventario:qr_imagen", args=[self.activo.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))
        self.assertEqual(response["Cache-Control"], "public, max-age=86400")


class QrEtiquetaPdfTests(EtiquetasQRBase):
    def test_no_autenticado_redirige_a_login(self):
        self.client.logout()
        response = self.client.get(reverse("inventario:etiqueta", args=[self.activo.pk]))
        self.assertEqual(response.status_code, 302)

    def test_tecnico_puede_generar_etiqueta(self):
        tecnico = crear_usuario("tecnico")
        self.client.force_login(tecnico)
        with self._enter_pdf():
            response = self.client.get(reverse("inventario:etiqueta", args=[self.activo.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response.content, b"%PDF-1.4 fake-etiqueta")
        self.assertIn("etiqueta_SN-TEST-001.pdf", response["Content-Disposition"])

    def test_etiqueta_inexistente_404(self):
        with self._enter_pdf():
            response = self.client.get(reverse("inventario:etiqueta", args=[99999]))
        self.assertEqual(response.status_code, 404)


class QrEtiquetasMasivasTests(EtiquetasQRBase):
    def setUp(self):
        super().setUp()
        self.activo2 = crear_activo("SN-TEST-002", tipo_dispositivo="monitor")

    def test_no_autenticado_redirige_a_login(self):
        self.client.logout()
        response = self.client.get(reverse("inventario:etiquetas"))
        self.assertEqual(response.status_code, 302)

    def test_get_muestra_lista_de_activos(self):
        response = self.client.get(reverse("inventario:etiquetas"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SN-TEST-001")
        self.assertContains(response, "SN-TEST-002")

    def test_post_genera_pdf_de_seleccion(self):
        with self._enter_pdf():
            response = self.client.post(
                reverse("inventario:etiquetas"),
                {"activos": [self.activo.pk, self.activo2.pk]},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("etiquetas_qr.pdf", response["Content-Disposition"])

    def test_post_sin_seleccion_redirige_con_error(self):
        response = self.client.post(reverse("inventario:etiquetas"), {"activos": []})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("inventario:etiquetas"), response.url)


class EtiquetaTemplateTests(EtiquetasQRBase):
    def test_etiqueta_context_genera_qr_y_la_plantilla_renderiza(self):
        request = RequestFactory().get("/")
        label = _etiqueta_context(request, self.activo)
        self.assertTrue(label["qr"].startswith("data:image/png;base64,"))
        self.assertEqual(label["serial"], "SN-TEST-001")
        self.assertEqual(label["numero_interno"], self.activo.numero_interno)
        self.assertEqual(label["logo_path"].endswith("logo_redihos_mark.png"), True)
        self.assertEqual(label["config"].nombre_empresa, "REDIHOS S.A.S")

        html = render_to_string("inventario/etiqueta_pdf.html", {"labels": [label]})
        self.assertIn("SN-TEST-001", html)
        self.assertIn("data:image/png;base64,", html)
        self.assertIn("REDIHOS S.A.S", html)
        self.assertIn(f"Activo fijo No.<strong>{self.activo.numero_interno}</strong>", html)
        self.assertIn("logo_redihos_mark.png", html)
        self.assertNotIn("Ubicacion", html)
        self.assertNotIn(">Estado<", html)


class NumeroInternoTests(TestCase):
    def test_autogenera_secuencial_desde_1000(self):
        a1 = crear_activo("SN-NUM-001")
        a2 = crear_activo("SN-NUM-002")
        self.assertEqual(a1.numero_interno, 1000)
        self.assertEqual(a2.numero_interno, 1001)

    def test_no_reaasigna_en_edicion(self):
        a1 = crear_activo("SN-NUM-003")
        original = a1.numero_interno
        a1.modelo = "Actualizado"
        a1.save()
        a1.refresh_from_db()
        self.assertEqual(a1.numero_interno, original)


class AsignacionActaEmailTests(TestCase):
    def setUp(self):
        self.usuario = crear_usuario("superadmin")
        self.client.force_login(self.usuario)
        self.activo = crear_activo("SN-ACTA-001")
        self.persona = Usuario.objects.create(
            nombre_completo="Pepe Pruebas",
            documento_identidad="123456789",
            cargo="Analista",
            area="Compras",
            correo="pepe@test.com",
        )

    def test_asignar_encola_email_de_acta(self):
        with patch("inventario.views.encolar_email") as mock:
            resp = self.client.post(
                reverse("inventario:asignar", args=[self.activo.pk]),
                {"usuario": self.persona.pk},
            )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(mock.called)
        args, kwargs = mock.call_args
        self.assertEqual(args[0], "pepe@test.com")
        self.assertIn(self.activo.serial, args[1])
        self.assertEqual(kwargs["adjunto_tipo"], "acta")
        self.assertIsNotNone(kwargs["adjunto_objeto_id"])

    def test_asignar_sin_correo_no_es_error(self):
        self.persona.correo = ""
        self.persona.save()
        resp = self.client.post(
            reverse("inventario:asignar", args=[self.activo.pk]),
            {"usuario": self.persona.pk},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.activo.asignaciones.filter(activa=True).count(), 1)


SOFTWARE_FALSO = [
    {"name": "Google Chrome", "version": "153.0.8010.54", "publisher": "Google LLC"},
    {"name": "Microsoft Visual C++ 2015 Redistributable", "version": "14.0.24215",
     "publisher": "Microsoft Corporation"},
    {"name": "Kaspersky Security Center", "version": "15.1.0", "publisher": "Kaspersky"},
    {"name": "DMS Office", "version": "Unavailable", "publisher": "Unavailable"},
    {"name": "7-Zip", "version": "23.01", "publisher": "Igor Pavlov"},
]


class SoftwareInventarioBase(TestCase):
    def setUp(self):
        from yule.models import EquipoOCS

        self.usuario = crear_usuario("superadmin")
        self.client.force_login(self.usuario)
        self.activo = crear_activo("SN-SW-001", nombre_equipo="W11F35F")
        self.equipo = EquipoOCS.objects.create(
            id_ocs="3",
            nombre_host="W11F35F",
            serial_bios="F35F284",
            activo_local=self.activo,
        )

    def url(self):
        return reverse("inventario:software", args=[self.activo.pk])


class SoftwareInventarioBase(TestCase):
    def setUp(self):
        from yule.models import EquipoOCS

        self.usuario = crear_usuario("superadmin")
        self.client.force_login(self.usuario)
        self.activo = crear_activo("SN-SW-001", nombre_equipo="W11F35F")
        self.equipo = EquipoOCS.objects.create(
            id_ocs="3",
            nombre_host="W11F35F",
            serial_bios="F35F284",
            activo_local=self.activo,
        )

    def url(self):
        return reverse("inventario:software", args=[self.activo.pk])

    def sembrar(self, software=SOFTWARE_FALSO):
        """Deja el activo con el software guardado, sin pasar por OCS."""
        from inventario.software_sync import aplicar_reporte

        return aplicar_reporte(self.activo, software)


class SoftwareEnBaseTests(SoftwareInventarioBase):
    """La vista lee de la base, no de OCS."""

    def test_lista_el_software_guardado(self):
        self.sembrar()
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total"], 5)
        self.assertEqual(resp.context["estado"], "ok")
        self.assertContains(resp, "Google Chrome")
        self.assertContains(resp, "7-Zip")

    def test_sin_lectura_previa_no_pelea_contra_ocs(self):
        # Abrir la página no debe pegarle a OCS: el inventario se guarda aparte.
        with patch("mantenimiento.services.build_client") as bc:
            resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total"], 0)
        self.assertContains(resp, "Todavía no se ha leído el software")
        bc.assert_not_called()

    def test_ordena_alfabeticamente(self):
        self.sembrar([
            {"name": "Zebra", "version": "1", "publisher": "X"},
            {"name": "Alfa", "version": "1", "publisher": "X"},
            {"name": "Media", "version": "1", "publisher": "X"},
        ])
        resp = self.client.get(self.url())
        nombres = [s.nombre for s in resp.context["software"]]
        self.assertEqual(nombres, ["Alfa", "Media", "Zebra"])

    def test_filtra_por_nombre_version_o_fabricante(self):
        self.sembrar()

        por_nombre = self.client.get(self.url(), {"q": "chrome"})
        self.assertEqual([s.nombre for s in por_nombre.context["software"]], ["Google Chrome"])

        por_fabricante = self.client.get(self.url(), {"q": "kaspersky"})
        self.assertEqual([s.nombre for s in por_fabricante.context["software"]],
                         ["Kaspersky Security Center"])

        por_version = self.client.get(self.url(), {"q": "23.01"})
        self.assertEqual([s.nombre for s in por_version.context["software"]], ["7-Zip"])

    def test_filtro_sin_coincidencias_no_es_error(self):
        self.sembrar()
        resp = self.client.get(self.url(), {"q": "programa-que-no-existe"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total"], 0)
        self.assertEqual(resp.context["total_guardado"], 5)
        self.assertEqual(resp.context["oculto"], 5)

    def test_version_unavailable_se_guarda_como_vacio(self):
        self.sembrar()
        dms = SoftwareInstalado.objects.get(activo=self.activo, nombre="DMS Office")
        # OCS devuelve la cadena "Unavailable" cuando el agente no reporta el
        # dato. Si se guardara, en la siguiente vuelta el programa aparecería
        # como versión nueva y como baja de la anterior.
        self.assertEqual(dms.version, "")
        self.assertEqual(dms.fabricante, "")
        resp = self.client.get(self.url())
        self.assertNotIn(">Unavailable<", resp.content.decode())

    def test_activo_sin_equipo_ocs_explica_el_motivo(self):
        self.equipo.activo_local = None
        self.equipo.save()
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["estado"], "sin_equipo")
        self.assertContains(resp, "no está vinculado a ningún equipo de OCS")
        # Sin equipo OCS no es una falla: el encabezado no debe alarmar al
        # usuario con un "No se pudo obtener" que sugiere un problema.
        self.assertContains(resp, "Este activo no tiene inventario de software")
        self.assertNotContains(resp, "No se pudo obtener el inventario de software")
        # Y no debe pintar una tabla vacía que parezca un equipo sin programas.
        # "tabla-software" aparece en el <script>, así que se mira el id de la
        # tabla en sí, que solo existe si se renderizó el listado.
        self.assertNotContains(resp, 'id="tabla-software"')

    def test_requiere_lectura_de_inventario(self):
        self.client.logout()
        resp = self.client.get(self.url())
        self.assertIn(resp.status_code, (302, 403))

    def test_activo_inexistente_da_404(self):
        self.client.logout()
        self.client.force_login(self.usuario)
        resp = self.client.get(reverse("inventario:software", args=[999999]))
        self.assertEqual(resp.status_code, 404)

    def test_el_detalle_del_activo_enlaza_al_software(self):
        resp = self.client.get(reverse("inventario:detalle", args=[self.activo.pk]))
        self.assertContains(resp, reverse("inventario:software", args=[self.activo.pk]))


class AplicarReporteTests(SoftwareInventarioBase):
    """Solo se escriben las diferencias entre el reporte y lo guardado."""

    def test_primer_reporte_registra_todo_nuevo(self):
        resumen = self.sembrar()
        self.assertEqual(resumen["nuevos"], 5)
        self.assertEqual(SoftwareInstalado.objects.filter(activo=self.activo).count(), 5)

    def test_reporte_identico_no_escribe_nada(self):
        self.sembrar()
        resumen = self.sembrar()
        self.assertEqual(resumen["nuevos"], 0)
        self.assertEqual(resumen["desinstalados"], 0)
        self.assertEqual(resumen["sin_cambios"], 5)
        # La clave del requisito: sin cambios no hay escrituras.
        self.assertEqual(SoftwareInstalado.objects.filter(activo=self.activo).count(), 5)

    def test_registra_solo_el_programa_nuevo(self):
        self.sembrar()
        nuevo = list(SOFTWARE_FALSO) + [
            {"name": "AnyDesk", "version": "9.0", "publisher": "AnyDesk Software"}
        ]
        resumen = self.sembrar(nuevo)
        self.assertEqual(resumen["nuevos"], 1)
        self.assertTrue(SoftwareInstalado.objects.filter(nombre="AnyDesk").exists())

    def test_cambio_de_version_da_de_baja_la_anterior(self):
        self.sembrar()
        actualizado = [
            dict(item, version="24.02") if item["name"] == "7-Zip" else item
            for item in SOFTWARE_FALSO
        ]
        resumen = self.sembrar(actualizado)

        self.assertEqual(resumen["nuevos"], 1)
        self.assertEqual(resumen["desinstalados"], 1)
        vieja = SoftwareInstalado.objects.get(activo=self.activo, nombre="7-Zip", version="23.01")
        self.assertFalse(vieja.presente)
        self.assertIsNotNone(vieja.fecha_retiro)
        nueva = SoftwareInstalado.objects.get(activo=self.activo, nombre="7-Zip", version="24.02")
        self.assertTrue(nueva.presente)
        # La baja no se cuenta como programa nuevo: solo hay 5 presentes.
        self.assertEqual(SoftwareInstalado.objects.filter(activo=self.activo, presente=True).count(), 5)

    def test_programa_desinstalado_se_conserva_con_fecha_de_retiro(self):
        self.sembrar()
        resumen = self.sembrar([i for i in SOFTWARE_FALSO if i["name"] != "7-Zip"])
        self.assertEqual(resumen["desinstalados"], 1)
        fila = SoftwareInstalado.objects.get(activo=self.activo, nombre="7-Zip")
        self.assertFalse(fila.presente)
        self.assertIsNotNone(fila.fecha_retiro)

    def test_reinstalacion_actualiza_la_fecha_de_instalacion(self):
        self.sembrar()
        self.sembrar([i for i in SOFTWARE_FALSO if i["name"] != "7-Zip"])
        antes = SoftwareInstalado.objects.get(activo=self.activo, nombre="7-Zip")

        resumen = self.sembrar()
        self.assertEqual(resumen["reinstalados"], 1)
        antes.refresh_from_db()
        self.assertTrue(antes.presente)
        self.assertIsNone(antes.fecha_retiro)
        # La fecha responde "¿cuándo se instaló?", no "¿cuándo lo vimos?".
        self.assertGreater(antes.fecha_instalacion, antes.fecha_ultima_vista - timezone.timedelta(days=1))

    def test_dos_versiones_del_mismo_programa_coexisten(self):
        # Windows instala runtimes de 32 y 64 bits del mismo nombre a la vez, y
        # el reporte trae los dos. No es un cambio ni una baja.
        self.sembrar()
        resumen = self.sembrar(list(SOFTWARE_FALSO) + [
            {"name": "Microsoft Visual C++ 2015 Redistributable", "version": "14.0.40664",
             "publisher": "Microsoft Corporation"}
        ])
        self.assertEqual(resumen["coexistencia"], 1)
        self.assertEqual(resumen["nuevos"], 0)
        self.assertEqual(resumen["desinstalados"], 0)
        # Quedan las dos versiones activas: 6 programas presentes.
        self.assertEqual(SoftwareInstalado.objects.filter(activo=self.activo, presente=True).count(), 6)

    def test_version_duplicada_en_el_reporte_no_genera_fila(self):
        self.sembrar()
        self.sembrar(list(SOFTWARE_FALSO) + [dict(SOFTWARE_FALSO[0])])
        self.assertEqual(SoftwareInstalado.objects.filter(activo=self.activo).count(), 5)

    def test_ignora_entradas_sin_nombre(self):
        resumen = self.sembrar([{"name": "", "version": "1", "publisher": "X"}])
        self.assertEqual(resumen["nuevos"], 0)
        self.assertEqual(SoftwareInstalado.objects.filter(activo=self.activo).count(), 0)

    def test_unavailable_no_produce_cambio_de_version(self):
        # El agente a veces deja de reportar la versión. Si se guardara el
        # texto, el programa aparecería como versión nueva y la anterior como
        # desinstalada, un cambio falso en cada vuelta.
        self.sembrar()
        base = SoftwareInstalado.objects.get(activo=self.activo, nombre="7-Zip")
        self.sembrar([dict(item, version="Unavailable") if item["name"] == "7-Zip" else item
                      for item in SOFTWARE_FALSO])
        self.assertEqual(SoftwareInstalado.objects.filter(activo=self.activo, nombre="7-Zip").count(), 1)
        base.refresh_from_db()
        self.assertTrue(base.presente)
        self.assertEqual(base.version, "23.01")


class RefrescarTests(SoftwareInventarioBase):
    """El botón "Leer de OCS": con reporte escribe, sin reporte no toca nada."""

    def test_actualizar_consulta_ocs_y_guarda(self):
        with patch("mantenimiento.services.build_client") as bc:
            bc.return_value.is_configured.return_value = True
            bc.return_value.get_software.return_value = list(SOFTWARE_FALSO)
            resp = self.client.get(self.url(), {"actualizar": 1})
        self.assertEqual(resp.status_code, 200)
        bc.return_value.get_software.assert_called_once_with("3")
        self.assertEqual(SoftwareInstalado.objects.filter(activo=self.activo).count(), 5)
        self.assertContains(resp, "5 cambios guardados")

    def test_actualizar_sin_cambios_lo_dice(self):
        with patch("mantenimiento.services.build_client") as bc:
            bc.return_value.is_configured.return_value = True
            bc.return_value.get_software.return_value = list(SOFTWARE_FALSO)
            self.client.get(self.url(), {"actualizar": 1})
            resp = self.client.get(self.url(), {"actualizar": 1})
        self.assertContains(resp, "no hubo cambios en OCS")

    def test_ocs_caido_no_borra_el_inventario_guardado(self):
        from yule.client import OCSClientException

        self.sembrar()
        with patch("mantenimiento.services.build_client") as bc:
            bc.return_value.is_configured.return_value = True
            bc.return_value.get_software.side_effect = OCSClientException("timeout")
            resp = self.client.get(self.url(), {"actualizar": 1})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No se pudo obtener el inventario de software")
        # Este es el caso que importa: el equipo está apagado o OCS caído, no
        # desinstaló 5 programas. La base tiene que quedar intacta.
        self.assertEqual(
            SoftwareInstalado.objects.filter(activo=self.activo, presente=True).count(), 5
        )
        self.assertEqual(
            SoftwareInstalado.objects.filter(activo=self.activo, presente=False).count(), 0
        )

    def test_reporte_vacio_marca_todo_como_retirado(self):
        # Un reporte que llega vacío sí es información: el equipo reportó que no
        # tiene nada. No se confunde con OCS caído, que no llega a escribir.
        self.sembrar()
        with patch("mantenimiento.services.build_client") as bc:
            bc.return_value.is_configured.return_value = True
            bc.return_value.get_software.return_value = []
            self.client.get(self.url(), {"actualizar": 1})
        self.assertEqual(
            SoftwareInstalado.objects.filter(activo=self.activo, presente=True).count(), 0
        )
        self.assertEqual(
            SoftwareInstalado.objects.filter(activo=self.activo, presente=False).count(), 5
        )

    def test_ocs_no_configurado_no_toca_la_base(self):
        with patch("mantenimiento.services.build_client") as bc:
            bc.return_value.is_configured.return_value = False
            resp = self.client.get(self.url(), {"actualizar": 1})
        self.assertEqual(resp.context["estado"], "no_configurado")
        self.assertEqual(SoftwareInstalado.objects.count(), 0)


class SoftwareGlobalTests(SoftwareInventarioBase):
    """La consulta cruzada: el motivo de guardar el software en la base."""

    def setUp(self):
        super().setUp()
        self.otro = crear_activo("SN-SW-002", nombre_equipo="W11F36F")

    def test_cuenta_equipos_por_programa(self):
        from inventario.software_sync import aplicar_reporte

        aplicar_reporte(self.activo, list(SOFTWARE_FALSO))
        # El segundo equipo solo tiene Chrome y 7-Zip.
        aplicar_reporte(self.otro, [
            {"name": "Google Chrome", "version": "153.0.8010.54", "publisher": "Google LLC"},
            {"name": "7-Zip", "version": "23.01", "publisher": "Igor Pavlov"},
        ])
        resp = self.client.get(reverse("inventario:software_global"))
        self.assertEqual(resp.status_code, 200)
        conteo = {p["nombre"]: p["equipos"] for p in resp.context["programas"]}
        self.assertEqual(conteo["Google Chrome"], 2)
        self.assertEqual(conteo["7-Zip"], 2)
        self.assertEqual(conteo["Kaspersky Security Center"], 1)

    def test_no_cuenta_dos_versiones_del_mismo_programa(self):
        from inventario.software_sync import aplicar_reporte

        aplicar_reporte(self.activo, [
            {"name": "Runtime", "version": "1.0", "publisher": "X"},
            {"name": "Runtime", "version": "2.0", "publisher": "X"},
        ])
        resp = self.client.get(reverse("inventario:software_global"))
        conteo = {p["nombre"]: p["equipos"] for p in resp.context["programas"]}
        self.assertEqual(conteo["Runtime"], 1)

    def test_excluye_lo_que_ya_no_esta_instalado(self):
        from inventario.software_sync import aplicar_reporte

        aplicar_reporte(self.activo, list(SOFTWARE_FALSO))
        aplicar_reporte(self.activo, [i for i in SOFTWARE_FALSO if i["name"] != "7-Zip"])
        resp = self.client.get(reverse("inventario:software_global"))
        nombres = [p["nombre"] for p in resp.context["programas"]]
        self.assertNotIn("7-Zip", nombres)

    def test_busca_por_nombre_version_o_fabricante(self):
        from inventario.software_sync import aplicar_reporte

        aplicar_reporte(self.activo, list(SOFTWARE_FALSO))
        url = reverse("inventario:software_global")
        for q, esperado in (
            ("kaspersky", "Kaspersky Security Center"),
            ("153.0", "Google Chrome"),
            ("Igor", "7-Zip"),
        ):
            resp = self.client.get(url, {"q": q})
            nombres = [p["nombre"] for p in resp.context["programas"]]
            self.assertEqual(nombres, [esperado], f"buscar {q!r}")

    def test_requiere_lectura_de_inventario(self):
        self.client.logout()
        resp = self.client.get(reverse("inventario:software_global"))
        self.assertIn(resp.status_code, (302, 403))
