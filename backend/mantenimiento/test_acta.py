"""Acta de mantenimiento en una hoja carta (§B7 del diseño).

WeasyPrint no carga en Windows sin GTK: las pruebas de armado y de vistas lo
simulan con ``FAKE_WEASY``. ``ActaUnaHojaTests`` usa el WeasyPrint real y solo
corre donde está instalado (CI); deja los PDF de muestra en ``ACTA_MUESTRAS_DIR``
si esa variable existe.
"""

import io
import os
import tempfile
from datetime import date, datetime, timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageDraw

from administracion.models import ConfiguracionSistema
from mantenimiento.acta import (
    _render,
    columnas_checklist,
    contexto_acta,
    documento_acta,
    fotos_acta,
    observaciones_acta,
    renderizar_acta,
    resumen_checklist,
    url_hoja_de_vida,
)
from mantenimiento.ayudas_pruebas import asignar, crear_pc, crear_usuario
from mantenimiento.ejecucion import cerrar_orden, iniciar_preventivo, marcar_punto
from mantenimiento.models import FORMATO_ANTERIOR, FotoMantenimiento, OrdenMantenimiento, Repuesto

HOY = date(2026, 10, 23)
CREADA = timezone.make_aware(datetime(2026, 10, 23, 8, 0))


class FakeDocumento:
    pages = [object()]

    def write_pdf(self):
        return b"%PDF-1.4 acta-fake"


class FakeHTML:
    def __init__(self, *a, **kw):
        pass

    def render(self):
        return FakeDocumento()


FAKE_WEASY = type("M", (), {"HTML": FakeHTML})()


def _sin_ocs():
    return patch("mantenimiento.ejecucion.snapshot_software_ocs", return_value=[])


def _texto(n, frase="Se encontró desgaste en la pieza y se ajustó con cuidado; revisar de nuevo en el próximo preventivo. "):
    """Texto realista (con espacios) de exactamente ``n`` caracteres."""
    texto = (frase * (n // len(frase) + 1))[:n]
    return texto if texto[-1] != " " else texto[:-1] + "."


def _png(ancho=40, alto=30, color=(1, 86, 166), rotulo=""):
    imagen = Image.new("RGB", (ancho, alto), color)
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rectangle([ancho // 8, alto // 8, ancho * 7 // 8, alto * 7 // 8], outline=(255, 255, 255), width=max(1, ancho // 100))
    dibujo.ellipse([ancho // 3, alto // 3, ancho * 2 // 3, alto * 2 // 3], fill=(241, 245, 249))
    if rotulo:
        dibujo.text((ancho // 8 + 10, alto // 8 + 10), rotulo, fill=(255, 255, 255))
    salida = io.BytesIO()
    imagen.save(salida, format="PNG")
    return salida.getvalue()


def _foto(orden, minutos=0, descripcion="", en_acta=False, ancho=40, alto=30):
    """Foto de la orden con ``fecha_creacion`` = CREADA + ``minutos``."""
    foto = FotoMantenimiento.objects.create(
        orden=orden,
        foto=SimpleUploadedFile(f"foto_{minutos}.png", _png(ancho, alto, rotulo=descripcion), content_type="image/png"),
        descripcion=descripcion,
        en_acta=en_acta,
    )
    FotoMantenimiento.objects.filter(pk=foto.pk).update(fecha_creacion=CREADA + timedelta(minutes=minutos))
    foto.refresh_from_db()
    return foto


def _cerrar_preventivo(orden, tecnico, fallas=None, observaciones="", estado_final="operativo"):
    """Marca todo bien salvo ``fallas`` ({descripción: observación}) y cierra."""
    fallas = fallas or {}
    for item in orden.checklist_items.all():
        if item.descripcion in fallas:
            marcar_punto(item, "falla", fallas[item.descripcion])
        else:
            marcar_punto(item, "bien")
    cerrar_orden(orden, tecnico, fecha_cierre=HOY, estado_final=estado_final, observaciones=observaciones, hoy=HOY)
    orden.refresh_from_db()
    return orden


class MediaTemporal:
    """Guarda los archivos subidos en una carpeta temporal, no en ``media/``."""

    def setUp(self):
        super().setUp()
        carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(carpeta.cleanup)
        ajuste = override_settings(MEDIA_ROOT=carpeta.name)
        ajuste.enable()
        self.addCleanup(ajuste.disable)


class ArmadoActaTests(MediaTemporal, TestCase):
    def setUp(self):
        super().setUp()
        p = _sin_ocs()
        p.start()
        self.addCleanup(p.stop)
        config = ConfiguracionSistema.get_config()
        config.acta_mant_codigo = "FT-TEST"
        config.acta_mant_version = "03"
        config.save()
        self.tecnico = crear_usuario(first_name="Ana", last_name="Técnica", cargo="Analista de Sistemas")
        self.request = RequestFactory().get("/")
        self.pc = crear_pc(nombre_equipo="PT-12", ip_equipo="192.168.1.57")

    def _orden_cerrada(self, con_responsable=True):
        if con_responsable:
            asignar(self.pc)
        orden = iniciar_preventivo(self.pc, self.tecnico, HOY)
        return _cerrar_preventivo(orden, self.tecnico, fallas={"Bisagras": "Floja"}, observaciones="Revisar en 6 meses")

    def _html(self, orden):
        return render_to_string("mantenimiento/acta_pdf.html", contexto_acta(orden, self.request))

    def test_columnas_por_seccion(self):
        orden = self._orden_cerrada()
        izquierda, derecha = columnas_checklist(list(orden.checklist_items.all()))
        self.assertEqual([g["seccion"] for g in izquierda], ["Hardware", "Limpieza"])
        self.assertEqual([g["seccion"] for g in derecha], ["Mantenimiento lógico"])
        self.assertEqual([len(g["items"]) for g in izquierda + derecha], [4, 3, 5])
        # Los puntos se numeran seguidos, en el orden en que salen en el acta.
        numeros = [i.numero for g in izquierda + derecha for i in g["items"]]
        self.assertEqual(numeros, list(range(1, 13)))

    def test_columnas_no_parten_grupos(self):
        orden = iniciar_preventivo(self.pc, self.tecnico, HOY)
        items = list(orden.checklist_items.filter(seccion="Mantenimiento lógico"))
        izquierda, derecha = columnas_checklist(items)
        self.assertEqual([g["seccion"] for g in izquierda], ["Mantenimiento lógico"])
        self.assertEqual(derecha, [])
        self.assertEqual(columnas_checklist([]), ([], []))

    def test_observaciones_primero_las_fallas(self):
        orden = self._orden_cerrada()
        self.assertEqual(observaciones_acta(orden), ["Bisagras (falla): Floja", "Revisar en 6 meses"])
        OrdenMantenimiento.objects.filter(pk=orden.pk).update(observaciones="")
        orden.refresh_from_db()
        self.assertEqual(observaciones_acta(orden), ["Bisagras (falla): Floja"])

    def test_fotos_maximo_3_y_prioriza_marcadas(self):
        orden = iniciar_preventivo(self.pc, self.tecnico, HOY)
        f1 = _foto(orden, minutos=3, descripcion="Uno")
        f2 = _foto(orden, minutos=1, descripcion="Dos")
        f3 = _foto(orden, minutos=5, descripcion="Tres")
        f4 = _foto(orden, minutos=2, descripcion="Cuatro")
        f5 = _foto(orden, minutos=4, descripcion="Cinco")
        # Sin marcadas: las 3 primeras por fecha de creación.
        self.assertEqual(fotos_acta(orden), [f2, f4, f1])
        # Con marcadas: solo esas, aunque sean menos de 3.
        FotoMantenimiento.objects.filter(pk__in=[f3.pk, f5.pk]).update(en_acta=True)
        self.assertEqual(fotos_acta(orden), [f5, f3])
        # Nunca más de 3.
        FotoMantenimiento.objects.filter(orden=orden).update(en_acta=True)
        self.assertEqual(fotos_acta(orden), [f2, f4, f1])

        fotos = contexto_acta(orden, self.request)["fotos"]
        self.assertEqual([f["descripcion"] for f in fotos], ["Dos", "Cuatro", "Uno"])
        self.assertEqual(fotos[0]["path"], f2.foto.path)

    def test_resumen(self):
        orden = self._orden_cerrada()
        self.assertEqual(
            resumen_checklist(list(orden.checklist_items.all())),
            {"total": 12, "bien": 11, "falla": 1, "na": 0},
        )

    @override_settings(QR_BASE_URL="https://sysadmin.local:6060")
    def test_url_hoja_de_vida_usa_qr_base_url(self):
        url = url_hoja_de_vida(self.request, self.pc)
        self.assertTrue(url.startswith("https://sysadmin.local:6060/mantenimiento/hoja-de-vida/"), url)
        self.assertEqual(url, f"https://sysadmin.local:6060/mantenimiento/hoja-de-vida/{self.pc.pk}/")
        with override_settings(QR_BASE_URL=""):
            self.assertEqual(
                url_hoja_de_vida(self.request, self.pc),
                f"http://testserver/mantenimiento/hoja-de-vida/{self.pc.pk}/",
            )

    def test_contexto(self):
        orden = self._orden_cerrada()
        Repuesto.objects.create(orden=orden, nombre="Disco SSD 512 GB", cantidad=1, costo_unitario=250000)
        contexto = contexto_acta(orden, self.request, escala=2)
        self.assertEqual(contexto["numero"], f"{orden.pk:04d}")
        self.assertEqual(contexto["repuestos"], ["Disco SSD 512 GB × 1"])
        self.assertEqual(contexto["escala"], 2)
        self.assertFalse(contexto["es_correctivo"])
        self.assertEqual(contexto["datos"], orden.datos_acta)
        self.assertEqual(contexto["config"].acta_mant_codigo, "FT-TEST")
        self.assertTrue(contexto["qr"].startswith("data:image/png;base64,"))
        self.assertTrue(contexto["logo_path"].endswith("logo_redihos_mark.png"))

    def test_html_tiene_los_datos_y_no_tiene_columna_de_observacion(self):
        html = self._html(self._orden_cerrada())
        for texto in (
            "ACTA DE MANTENIMIENTO DE EQUIPOS DE CÓMPUTO",
            "Código: FT-TEST",
            "Versión: 03",
            "Página 1 de 1",
            "Marta López Gómez",
            "FALLA",
            "Bisagras (falla):",
            "3. CHECKLIST · 12 puntos · 11 bien · 1 con falla",
            "MANTENIMIENTO LÓGICO",
            "192.168.1.57",
            "Ana Técnica",
            "Analista de Sistemas",
            "SysAdmin · FT-TEST v03 · Acta de mantenimiento N°",
            "23/10/2026",
            "Ninguno",
            "Operativo",
            'class="escala-3"',
        ):
            self.assertIn(texto, html)
        self.assertNotIn(">Observación<", html)
        # Sin fotos, la sección de evidencia no aparece.
        self.assertNotIn("EVIDENCIA FOTOGRÁFICA", html)

    def test_codigo_y_version_vacios_muestran_raya(self):
        ConfiguracionSistema.objects.filter(pk=1).update(acta_mant_codigo="", acta_mant_version="")
        html = self._html(self._orden_cerrada())
        self.assertIn("Código: —", html)
        self.assertIn("Versión: —", html)

    def test_no_asignado_en_responsable_y_firma(self):
        html = self._html(self._orden_cerrada(con_responsable=False))
        self.assertEqual(html.count("No asignado"), 2)
        self.assertNotIn("Marta López Gómez", html)

    def test_correctivo_muestra_diagnostico_y_solucion(self):
        asignar(self.pc)
        orden = OrdenMantenimiento.objects.create(activo=self.pc, tipo="correctivo", estado="abierta", fecha_apertura=HOY)
        cerrar_orden(orden, self.tecnico, fecha_cierre=HOY, estado_final="fuera_servicio", observaciones="",
                     diagnostico="Disco con sectores dañados", acciones="Se cambió el disco", hoy=HOY)
        orden.refresh_from_db()
        html = self._html(orden)
        self.assertIn("DIAGNÓSTICO Y SOLUCIÓN", html)
        self.assertIn("Disco con sectores dañados", html)
        self.assertIn("Se cambió el disco", html)
        self.assertIn("Correctivo", html)
        self.assertNotIn("CHECKLIST", html)
        self.assertNotIn("Próximo", html)

    def test_fotos_y_repuestos_en_el_html(self):
        asignar(self.pc)
        orden = iniciar_preventivo(self.pc, self.tecnico, HOY)
        _foto(orden, minutos=1, descripcion="Antes · interior")
        Repuesto.objects.create(orden=orden, nombre="Teclado", cantidad=1)
        Repuesto.objects.create(orden=orden, nombre="Tornillo M2", cantidad=4)
        orden = _cerrar_preventivo(orden, self.tecnico)
        html = self._html(orden)
        self.assertIn("4. EVIDENCIA FOTOGRÁFICA", html)
        self.assertIn("Antes · interior", html)
        self.assertIn("file://", html)
        self.assertIn("Teclado × 1, Tornillo M2 × 4", html)
        self.assertIn("5. REPUESTOS Y ESTADO FINAL", html)
        self.assertIn("6. OBSERVACIONES", html)


class VistaActaTests(MediaTemporal, TestCase):
    def setUp(self):
        super().setUp()
        p = _sin_ocs()
        p.start()
        self.addCleanup(p.stop)
        self.tecnico = crear_usuario(first_name="Ana", last_name="Técnica", cargo="Analista de Sistemas")
        self.client.force_login(self.tecnico)
        self.pc = crear_pc()

    def _url(self, nombre, pk):
        return reverse(f"mantenimiento:{nombre}", args=[pk])

    def _get_pdf(self, orden):
        with patch.dict("sys.modules", {"weasyprint": FAKE_WEASY}):
            return self.client.get(self._url("acta_pdf", orden.pk))

    def test_solo_cerradas_de_formato_actual(self):
        abierta = iniciar_preventivo(self.pc, self.tecnico, HOY)
        self.assertRedirects(self._get_pdf(abierta), self._url("detalle_orden", abierta.pk))

        vieja = OrdenMantenimiento.objects.create(activo=self.pc, tipo="correctivo", estado="cerrada",
                                                  fecha_apertura=HOY, fecha_cierre=HOY, formato=FORMATO_ANTERIOR)
        self.assertRedirects(self._get_pdf(vieja), self._url("detalle_orden", vieja.pk))

        cerrada = _cerrar_preventivo(abierta, self.tecnico)
        resp = self._get_pdf(cerrada)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertEqual(resp.content, b"%PDF-1.4 acta-fake")
        self.assertEqual(
            resp["Content-Disposition"],
            f'inline; filename="acta_mantenimiento_{cerrada.pk:04d}_SN-PC-1.pdf"',
        )

    def test_lectura_puede_descargar_el_acta(self):
        orden = _cerrar_preventivo(iniciar_preventivo(self.pc, self.tecnico, HOY), self.tecnico)
        self.client.force_login(crear_usuario("lectura"))
        self.assertEqual(self._get_pdf(orden).status_code, 200)

    def test_cerrada_sin_datos_del_acta_redirige(self):
        orden = OrdenMantenimiento.objects.create(activo=self.pc, tipo="correctivo", estado="cerrada",
                                                  fecha_apertura=HOY, fecha_cierre=HOY)
        self.assertRedirects(self._get_pdf(orden), self._url("detalle_orden", orden.pk))

    def test_toggle_foto_acta_maximo_3(self):
        orden = iniciar_preventivo(self.pc, self.tecnico, HOY)
        fotos = [_foto(orden, minutos=i) for i in range(4)]
        for foto in fotos[:3]:
            resp = self.client.post(self._url("toggle_foto_acta", foto.pk))
            self.assertRedirects(resp, self._url("detalle_orden", orden.pk))
        resp = self.client.post(self._url("toggle_foto_acta", fotos[3].pk))
        self.assertRedirects(resp, self._url("detalle_orden", orden.pk))
        self.assertIn("Solo caben 3 fotos en el acta.", [str(m) for m in resp.wsgi_request._messages])
        self.assertEqual(
            list(FotoMantenimiento.objects.filter(orden=orden, en_acta=True).order_by("pk")),
            fotos[:3],
        )
        # Desmarcar una deja lugar para otra.
        self.client.post(self._url("toggle_foto_acta", fotos[0].pk))
        self.client.post(self._url("toggle_foto_acta", fotos[3].pk))
        self.assertEqual(
            list(FotoMantenimiento.objects.filter(orden=orden, en_acta=True).order_by("pk")),
            fotos[1:],
        )

    def test_toggle_foto_acta_pide_post_y_escritura(self):
        orden = iniciar_preventivo(self.pc, self.tecnico, HOY)
        foto = _foto(orden)
        self.assertEqual(self.client.get(self._url("toggle_foto_acta", foto.pk)).status_code, 405)
        self.client.force_login(crear_usuario("lectura"))
        resp = self.client.post(self._url("toggle_foto_acta", foto.pk))
        self.assertRedirects(resp, reverse("core:dashboard"), fetch_redirect_response=False)
        foto.refresh_from_db()
        self.assertFalse(foto.en_acta)

    def test_fotos_y_repuestos_bloqueados_en_orden_cerrada(self):
        orden = iniciar_preventivo(self.pc, self.tecnico, HOY)
        foto = _foto(orden, descripcion="Antes")
        repuesto = Repuesto.objects.create(orden=orden, nombre="Teclado", cantidad=1)
        orden = _cerrar_preventivo(orden, self.tecnico)
        detalle = self._url("detalle_orden", orden.pk)
        aviso = "Un mantenimiento cerrado no se modifica. Reábrelo si necesitas cambiarlo."

        intentos = [
            ("post", self._url("crear_foto", orden.pk),
             {"foto": SimpleUploadedFile("otra.png", _png(), content_type="image/png"), "descripcion": "Después"}),
            ("post", self._url("eliminar_foto", foto.pk), {}),
            ("post", self._url("toggle_foto_acta", foto.pk), {}),
            ("get", self._url("crear_repuesto", orden.pk), {}),
            ("post", self._url("crear_repuesto", orden.pk), {"orden": orden.pk, "nombre": "Mouse", "cantidad": 1}),
            ("get", self._url("editar_repuesto", repuesto.pk), {}),
            ("post", self._url("editar_repuesto", repuesto.pk), {"orden": orden.pk, "nombre": "Otro", "cantidad": 9}),
            ("post", self._url("eliminar_repuesto", repuesto.pk), {}),
        ]
        for metodo, url, datos in intentos:
            with self.subTest(url=url, metodo=metodo):
                resp = getattr(self.client, metodo)(url, datos)
                self.assertRedirects(resp, detalle)
                self.assertIn(aviso, [str(m) for m in resp.wsgi_request._messages])

        foto.refresh_from_db()
        repuesto.refresh_from_db()
        self.assertEqual(list(orden.fotos.all()), [foto])
        self.assertFalse(foto.en_acta)
        self.assertEqual(list(orden.repuestos.all()), [repuesto])
        self.assertEqual((repuesto.nombre, repuesto.cantidad), ("Teclado", 1))

        # El detalle de la orden cerrada no ofrece esos cambios.
        resp = self.client.get(detalle)
        for nombre, pk in (("crear_foto", orden.pk), ("eliminar_foto", foto.pk), ("toggle_foto_acta", foto.pk),
                           ("crear_repuesto", orden.pk), ("editar_repuesto", repuesto.pk),
                           ("eliminar_repuesto", repuesto.pk)):
            self.assertNotContains(resp, self._url(nombre, pk))

    def test_editar_repuesto_no_lo_mueve_a_otra_orden(self):
        orden = iniciar_preventivo(self.pc, self.tecnico, HOY)
        repuesto = Repuesto.objects.create(orden=orden, nombre="Teclado", cantidad=1)
        cerrada = OrdenMantenimiento.objects.create(activo=crear_pc("SN-OTRO"), tipo="correctivo", estado="cerrada",
                                                    fecha_apertura=HOY, fecha_cierre=HOY)
        resp = self.client.post(self._url("editar_repuesto", repuesto.pk),
                                {"orden": cerrada.pk, "nombre": "Teclado", "cantidad": 2})
        self.assertRedirects(resp, self._url("detalle_orden", orden.pk))
        repuesto.refresh_from_db()
        self.assertEqual((repuesto.orden_id, repuesto.cantidad), (orden.pk, 2))

    def test_detalle_abierta_tiene_interruptor_en_el_acta(self):
        orden = iniciar_preventivo(self.pc, self.tecnico, HOY)
        foto = _foto(orden, descripcion="Antes")
        resp = self.client.get(self._url("detalle_orden", orden.pk))
        self.assertContains(resp, self._url("toggle_foto_acta", foto.pk))
        self.assertContains(resp, "En el acta")
        self.assertContains(resp, self._url("crear_foto", orden.pk))
        self.assertContains(resp, self._url("crear_repuesto", orden.pk))
        # Abierta: todavía no hay acta que descargar.
        self.assertNotContains(resp, self._url("acta_pdf", orden.pk))
        self.assertNotContains(resp, self._url("orden_pdf", orden.pk))

    def test_detalle_enlaza_acta_o_pdf_anterior(self):
        orden = _cerrar_preventivo(iniciar_preventivo(self.pc, self.tecnico, HOY), self.tecnico)
        resp = self.client.get(self._url("detalle_orden", orden.pk))
        self.assertContains(resp, self._url("acta_pdf", orden.pk))
        self.assertContains(resp, "Descargar acta")
        self.assertNotContains(resp, self._url("orden_pdf", orden.pk))

        vieja = OrdenMantenimiento.objects.create(activo=self.pc, tipo="correctivo", estado="cerrada",
                                                  fecha_apertura=HOY, fecha_cierre=HOY, formato=FORMATO_ANTERIOR)
        resp = self.client.get(self._url("detalle_orden", vieja.pk))
        self.assertContains(resp, self._url("orden_pdf", vieja.pk))
        self.assertContains(resp, "PDF (formato anterior)")
        self.assertNotContains(resp, "Descargar acta")


def _weasyprint_real():
    try:
        import weasyprint  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


def _guardar_muestra(nombre, pdf):
    carpeta = os.environ.get("ACTA_MUESTRAS_DIR")
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
        with open(os.path.join(carpeta, nombre), "wb") as archivo:
            archivo.write(pdf)


MM_POR_PX = 25.4 / 96
ALTO_CARTA_MM = 279.4
MARGEN_MM = 10


def _caja(caja, clase):
    """Primera caja de WeasyPrint del elemento con ``clase``, o None.

    Recorre el árbol a mano porque ``descendants()`` no entra en las cajas con
    ``position: fixed`` (WeasyPrint las envuelve en un ``AbsolutePlaceholder``
    que guarda la caja real en ``_box``). WeasyPrint va fijo en 70.0.
    """
    caja = getattr(caja, "_box", caja)
    elemento = getattr(caja, "element", None)
    if elemento is not None and clase in (elemento.get("class") or "").split():
        return caja
    for hija in getattr(caja, "children", None) or ():
        encontrada = _caja(hija, clase)
        if encontrada is not None:
            return encontrada
    return None


def _extremos_mm(pagina, clase):
    """(arriba, abajo) del elemento con ``clase`` en la página, en mm desde el borde."""
    caja = _caja(pagina._page_box, clase)
    return caja.position_y * MM_POR_PX, (caja.position_y + caja.margin_height()) * MM_POR_PX


@skipUnless(_weasyprint_real(), "WeasyPrint real no disponible (Windows sin GTK)")
class ActaUnaHojaTests(MediaTemporal, TestCase):
    def setUp(self):
        super().setUp()
        p = _sin_ocs()
        p.start()
        self.addCleanup(p.stop)
        config = ConfiguracionSistema.get_config()
        config.acta_mant_codigo = "FT-TI-002"
        config.acta_mant_version = "01"
        config.save()
        self.request = RequestFactory().get("/")

    def _fotos(self, orden):
        for i, descripcion in enumerate(("Antes · interior", "Después · interior", "Bisagra izquierda")):
            _foto(orden, minutos=i, descripcion=descripcion, ancho=1600, alto=1200)

    def _documento(self, orden, escala):
        import weasyprint

        html = render_to_string("mantenimiento/acta_pdf.html", contexto_acta(orden, self.request, escala=escala))
        return weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).render()

    def _hueco_mm(self, documento):
        """Blanco entre el final de las observaciones y el comienzo de las firmas."""
        pagina = documento.pages[0]
        _, cuadro_abajo = _extremos_mm(pagina, "cuadro")
        firmas_arriba, _ = _extremos_mm(pagina, "firmas")
        return firmas_arriba - cuadro_abajo

    def _comprobar_firmas_al_pie(self, documento):
        """Una hoja; firmas en el tercio inferior, sin tapar las observaciones; pie pegado al margen de abajo."""
        self.assertEqual(len(documento.pages), 1)
        pagina = documento.pages[0]
        firmas_arriba, _ = _extremos_mm(pagina, "firmas")
        _, cuadro_abajo = _extremos_mm(pagina, "cuadro")
        _, pie_abajo = _extremos_mm(pagina, "pie")
        fondo_util = ALTO_CARTA_MM - MARGEN_MM
        self.assertGreaterEqual(firmas_arriba, ALTO_CARTA_MM * 2 / 3, "las firmas no quedaron en el tercio inferior")
        self.assertGreaterEqual(firmas_arriba, cuadro_abajo, "las firmas tapan las observaciones")
        self.assertLessEqual(pie_abajo, fondo_util + 0.5, "el pie se sale de la hoja")
        self.assertGreaterEqual(pie_abajo, fondo_util - 2, "el pie no quedó pegado al fondo de la hoja")

    def _orden_maxima(self, tecnico, responsable):
        """12 fallas de 150, observaciones de 600, 3 fotos y 5 repuestos de 150, con datos largos."""
        pc = crear_pc("5CD1234XYZ-0987654321", nombre_equipo="REDIHOS-PT12-CONTABILIDAD",
                      procesador="Intel(R) Core(TM) i7-1185G7 @ 3.00GHz", ram="32 GB DDR4 3200 MHz",
                      disco_capacidad="1 TB", tipo_disco="SSD NVMe", sistema_operativo="Windows 11 Pro 23H2",
                      ip_equipo="192.168.100.157", ubicacion_fisica="Sede principal, piso 3, oficina de contabilidad",
                      marca="Hewlett-Packard", modelo="EliteBook 840 G8 Notebook PC")
        asignar(pc, documento="1020304050", area="Contabilidad y finanzas", **responsable)
        orden = iniciar_preventivo(pc, tecnico, HOY)
        self._fotos(orden)
        for i in range(5):
            Repuesto.objects.create(orden=orden, nombre=_texto(150, f"Repuesto {i + 1} de referencia larga del fabricante con código. "), cantidad=10)
        fallas = {item.descripcion: _texto(150) for item in orden.checklist_items.all()}
        self.assertEqual(len(fallas), 12)
        return _cerrar_preventivo(orden, tecnico, fallas=fallas, observaciones=_texto(600),
                                  estado_final="operativo_obs")

    def test_contenido_tipico_usa_la_letra_mas_grande_que_cabe(self):
        tecnico = crear_usuario(first_name="Bairon", last_name="Calle", cargo="Analista de Sistemas")
        pc = crear_pc("5CD1234XYZ", nombre_equipo="REDIHOS-PT12", procesador="Intel Core i5-1135G7", ram="16 GB",
                      disco_capacidad="512 GB", tipo_disco="SSD", sistema_operativo="Windows 11 Pro",
                      ip_equipo="192.168.1.57", ubicacion_fisica="Oficina principal", modelo="ProBook 440 G8")
        asignar(pc)
        orden = iniciar_preventivo(pc, tecnico, HOY)
        self._fotos(orden)
        Repuesto.objects.create(orden=orden, nombre="Tornillo de bisagra", cantidad=2)
        orden = _cerrar_preventivo(
            orden, tecnico,
            fallas={"Bisagras": _texto(60), "Batería": _texto(60)},
            observaciones=_texto(200, "Usar el equipo sobre una superficie plana para no tapar la ventilación. "),
        )
        pdf, escala = renderizar_acta(orden, self.request)
        _guardar_muestra("acta_tipica.pdf", pdf)
        self.assertTrue(pdf.startswith(b"%PDF"))
        documento, _escala = documento_acta(orden, self.request)
        self._comprobar_firmas_al_pie(documento)
        # Dinámico: la elegida cabe y la anterior (letra más grande) ya no.
        if escala > 0:
            self.assertGreater(
                len(self._documento(orden, escala - 1).pages), 1,
                f"la escala {escala - 1} también cabía: se eligió letra más chica de la necesaria",
            )

    def test_un_acta_corta_llena_la_hoja_y_no_deja_hueco(self):
        """Lo que motivó el cambio: un acta corta dejaba ~5 cm de blanco antes de las firmas."""
        tecnico = crear_usuario(first_name="Ana", last_name="Pérez Díaz", cargo="Técnica de Soporte")
        pc = crear_pc("SN-CORTA-1", nombre_equipo="REDIHOS-PT20", modelo="ProBook 440 G8")
        asignar(pc)
        orden = iniciar_preventivo(pc, tecnico, HOY)
        orden = _cerrar_preventivo(orden, tecnico, observaciones="Sin novedades.")

        documento, escala = documento_acta(orden, self.request)
        self.assertEqual(len(documento.pages), 1)
        self._comprobar_firmas_al_pie(documento)
        hueco = self._hueco_mm(documento)
        self.assertLessEqual(hueco, 8, f"quedaron {hueco:.1f} mm de blanco antes de las firmas")

        # Y sin estirar el cuadro el hueco era grande: así se ve que el paso 2 sirve.
        sin_estirar = _render(contexto_acta(orden, self.request, escala=escala), escala)
        self.assertGreater(self._hueco_mm(sin_estirar), 20)

    def test_contenido_maximo_cabe_en_una_hoja(self):
        tecnico = crear_usuario(first_name="María Fernanda", last_name="Restrepo Villalobos",
                                cargo="Coordinadora de Infraestructura Tecnológica")
        orden = self._orden_maxima(tecnico, {"nombre": "María Alejandra Castañeda Villarreal",
                                             "cargo": "Auxiliar contable de cuentas por pagar"})
        pdf, escala = renderizar_acta(orden, self.request)
        _guardar_muestra("acta_maxima.pdf", pdf)
        self.assertTrue(pdf.startswith(b"%PDF"))
        documento, _escala = documento_acta(orden, self.request)
        self._comprobar_firmas_al_pie(documento)
        self.assertGreaterEqual(escala, 3, "el contenido máximo debería necesitar letra chica")

    def test_nombres_de_dos_renglones_no_tapan_las_observaciones(self):
        # Nombre y cargo se parten en dos renglones en las dos firmas: el bloque
        # fijo de firmas crece hacia arriba y no debe pisar el contenido.
        tecnico = crear_usuario(first_name="María Fernanda de los Ángeles", last_name="Restrepo Villalobos de la Torre",
                                cargo="Coordinadora de Infraestructura Tecnológica y Seguridad de la Información")
        orden = self._orden_maxima(tecnico, {
            "nombre": "María Alejandra del Socorro Castañeda Villarreal de Montoya",
            "cargo": "Auxiliar contable de cuentas por pagar y conciliaciones bancarias",
        })
        _pdf, escala = renderizar_acta(orden, self.request)
        self._comprobar_firmas_al_pie(self._documento(orden, escala))
        # En escala 0 (2 páginas con este contenido) los renglones dobles sí se ven:
        # el bloque sigue cabiendo en la reserva.
        documento = self._documento(orden, 0)
        pagina = documento.pages[-1]
        reserva_arriba, reserva_abajo = _extremos_mm(pagina, "reserva")
        firmas_arriba, _ = _extremos_mm(pagina, "firmas")
        _, pie_abajo = _extremos_mm(pagina, "pie")
        self.assertLessEqual(pie_abajo - firmas_arriba, reserva_abajo - reserva_arriba)
