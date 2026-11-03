"""Pruebas de lo que apaga un módulo.

Un módulo apagado deja de existir: sus URLs responden 404, no una redirección,
y eso vale también para el superadministrador y para las páginas públicas del
módulo (el formulario de reporte de soporte, por ejemplo) —
``ModuloActivoMiddleware``. Y desaparece del menú lateral y del tablero, que se
pintan desde el catálogo de módulos y los permisos del rol, no desde HTML a mano.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import ResolverMatch, reverse

from administracion.context_processors import menu_modulos
from administracion.middleware import APPS_SIEMPRE_ABIERTAS, ModuloActivoMiddleware
from administracion.models import Modulo, PermisoRol
from administracion.registro import invalidar_cache
from accounts.permisos import APP_A_MODULO


class _BaseModulosTests(TestCase):
    def setUp(self):
        # La caché sobrevive al rollback de cada prueba: se limpia antes y
        # después para no filtrar estado entre pruebas. Además, update() no
        # dispara señales, así que cada cambio masivo se cierra con
        # invalidar_cache().
        invalidar_cache()
        self.addCleanup(invalidar_cache)
        self.superadmin = get_user_model().objects.create_user(
            username="super_modulos", password="x", rol="superadmin"
        )
        self.client.force_login(self.superadmin)

    def apagar(self, *claves):
        Modulo.objects.filter(clave__in=claves).update(activo=False)
        invalidar_cache()

    def encender(self, *claves):
        Modulo.objects.filter(clave__in=claves).update(activo=True)
        invalidar_cache()

    def crear_usuario(self, rol):
        return get_user_model().objects.create_user(
            username=f"modulos_{rol}", password="x", rol=rol
        )


class MiddlewareModulosTests(_BaseModulosTests):
    def test_un_modulo_inactivo_responde_404(self):
        # licencias nace apagada: no hay que tocarla.
        self.assertFalse(Modulo.objects.get(clave="licencias").activo)
        resp = self.client.get(reverse("licencias:lista"))
        self.assertEqual(resp.status_code, 404)

    def test_404_y_no_redireccion(self):
        resp = self.client.get(reverse("licencias:lista"))
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn("Location", resp.headers)

    def test_tambien_404_para_el_superadministrador(self):
        self.assertEqual(self.superadmin.rol, "superadmin")
        resp = self.client.get(reverse("licencias:lista"))
        self.assertEqual(resp.status_code, 404)

    def test_un_modulo_activo_responde_200(self):
        self.assertTrue(Modulo.objects.get(clave="inventario").activo)
        resp = self.client.get(reverse("inventario:lista"))
        self.assertEqual(resp.status_code, 200)

    def test_reactivar_vuelve_a_dar_200(self):
        self.assertEqual(self.client.get(reverse("licencias:lista")).status_code, 404)
        self.encender("licencias")
        self.assertEqual(self.client.get(reverse("licencias:lista")).status_code, 200)

    def test_con_todos_los_modulos_inactivos_el_login_sigue_vivo(self):
        """El 404 no puede comerse el acceso: sin login nadie reactiva nada."""
        claves = list(
            Modulo.objects.filter(es_esencial=False).values_list("clave", flat=True)
        )
        self.assertTrue(claves)  # hay módulos que apagar
        self.apagar(*claves)

        # Sin sesión: la pantalla de login responde.
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)

        # Con sesión: las páginas del núcleo siguen vivas.
        self.client.force_login(self.superadmin)
        for ruta in (
            "core:dashboard",
            "notificaciones:lista",
            "administracion:lista_auditoria",
        ):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(reverse(ruta)).status_code, 200)

    def test_el_formulario_publico_de_soporte_muere_con_su_modulo(self):
        self.client.logout()  # el formulario es público
        url = reverse("soporte:reportar_publico")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.apagar("soporte")
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_reports_responde_a_la_clave_reportes(self):
        """``reports`` (app_name) y ``reportes`` (clave) no coinciden; se mapea."""
        url = reverse("reports:index")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.apagar("reportes")
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_un_modulo_inactivo_tambien_es_404_sin_sesion(self):
        """La URL deja de existir para todos, no solo para quien tiene sesión."""
        self.client.logout()
        resp = self.client.get(reverse("licencias:lista"))
        self.assertEqual(resp.status_code, 404)

    def test_una_url_sin_app_name_no_se_filtra(self):
        """/media/ y similares no tienen namespace: el filtro las deja pasar."""
        self.apagar(*Modulo.objects.filter(es_esencial=False).values_list("clave", flat=True))
        middleware = ModuloActivoMiddleware(lambda request: HttpResponse())
        request = RequestFactory().get("/media/x")

        # Sin resolver_match (la URL no resolvió): se deja pasar.
        request.resolver_match = None
        self.assertIsNone(middleware.process_view(request, None, (), {}))

        # Resuelta, pero sin app_name.
        request.resolver_match = ResolverMatch(lambda r: None, (), {}, url_name="media")
        self.assertEqual(request.resolver_match.app_name, "")
        self.assertIsNone(middleware.process_view(request, None, (), {}))

        # Con app_name que no pertenece a ningún módulo.
        request.resolver_match = ResolverMatch(
            lambda r: None, (), {}, url_name="algo", app_names=["inventado"]
        )
        self.assertIsNone(middleware.process_view(request, None, (), {}))

    def test_las_apps_siempre_abiertas_no_son_modulos(self):
        """Nada de lo que el filtro exime puede ser, a la vez, un módulo apagable."""
        self.assertFalse(APPS_SIEMPRE_ABIERTAS & set(APP_A_MODULO))


class UrlsModuloInactivoTests(_BaseModulosTests):
    def test_las_urls_de_un_modulo_inactivo_dan_404(self):
        # licencias y prestamos nacen apagados: no se tocan.
        for ruta in (
            "licencias:lista",
            "licencias:crear",
            "licencias:exportar_excel",
            "prestamos:lista",
            "prestamos:crear",
        ):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(reverse(ruta)).status_code, 404)


def _enlace(nombre_url):
    """El atributo href tal como lo pinta el menú, para no confundir una URL con otra."""
    return f'href="{reverse(nombre_url)}"'


class MenuPorDatosTests(_BaseModulosTests):
    """El menú lateral sale del catálogo de módulos y de los permisos del rol."""

    def html_del_tablero(self):
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def test_el_menu_no_muestra_un_modulo_inactivo(self):
        html = self.html_del_tablero()
        self.assertIn(_enlace("inventario:lista"), html)  # el menú sí se pintó
        self.assertNotIn(_enlace("licencias:lista"), html)
        self.assertNotIn(_enlace("prestamos:lista"), html)

    def test_el_menu_respeta_los_permisos_del_rol(self):
        self.client.force_login(self.crear_usuario("tecnico"))
        html = self.html_del_tablero()
        self.assertIn(_enlace("inventario:lista"), html)
        # passwords y administracion son "ninguno" para el técnico
        self.assertNotIn(_enlace("passwords:index"), html)
        self.assertNotIn(_enlace("administracion:lista_auditoria"), html)

    def test_un_cambio_en_la_matriz_cambia_el_menu_sin_reiniciar(self):
        self.client.force_login(self.crear_usuario("tecnico"))
        self.assertIn(_enlace("usuarios:lista"), self.html_del_tablero())
        celda = PermisoRol.objects.get(rol__clave="tecnico", modulo="usuarios")
        celda.nivel = "ninguno"
        celda.save()  # la señal invalida la caché
        self.assertNotIn(_enlace("usuarios:lista"), self.html_del_tablero())

    def test_el_menu_sigue_el_orden_del_catalogo(self):
        self.encender("licencias", "prestamos")
        html = self.html_del_tablero()
        posiciones = [
            html.index(_enlace(modulo.url_nombre)) for modulo in Modulo.objects.order_by("orden")
        ]
        self.assertEqual(posiciones, sorted(posiciones))

        # Cambiar el orden en la tabla cambia el menú.
        soporte = Modulo.objects.get(clave="soporte")
        soporte.orden = 5
        soporte.save()
        html = self.html_del_tablero()
        self.assertLess(
            html.index(_enlace("soporte:lista")), html.index(_enlace("usuarios:lista"))
        )

    def test_el_menu_no_repite_una_consulta_por_modulo(self):
        request = RequestFactory().get("/")
        request.user = self.crear_usuario("tecnico")  # no es superadmin: lee la matriz
        invalidar_cache()
        with CaptureQueriesContext(connection) as en_frio:
            opciones = list(menu_modulos(request)["menu_modulos"])
        self.assertGreater(len(opciones), 3)  # el menú no salió vacío
        # catálogo + módulos activos + matriz: tres, nunca una por módulo.
        self.assertLessEqual(len(en_frio), 3)
        # Con la caché caliente el menú no toca la base.
        with self.assertNumQueries(0):
            self.assertEqual(list(menu_modulos(request)["menu_modulos"]), opciones)

    def test_activar_un_modulo_lo_hace_aparecer_sin_reiniciar(self):
        self.assertNotIn(_enlace("licencias:lista"), self.html_del_tablero())
        self.encender("licencias")
        self.assertIn(_enlace("licencias:lista"), self.html_del_tablero())

    def test_el_menu_marca_la_seccion_actual(self):
        for nombre_url in ("inventario:lista", "reports:index"):
            with self.subTest(url=nombre_url):
                html = self.client.get(reverse(nombre_url)).content.decode()
                self.assertIn(f'<a class="nav-link active" {_enlace(nombre_url)}>', html)
                self.assertEqual(html.count("nav-link active"), 1)

    def test_yule_sigue_siendo_un_enlace_fijo_de_inventario(self):
        """No es un módulo: sale con el permiso de inventario y se marca solo."""
        html = self.client.get(reverse("yule:index")).content.decode()
        self.assertIn(f'<a class="nav-link active" {_enlace("yule:index")}>', html)
        self.assertEqual(html.count("nav-link active"), 1)  # inventario no se marca

        # Un rol sin inventario no ve a Yule.
        celda = PermisoRol.objects.get(rol__clave="lectura", modulo="inventario")
        celda.nivel = "ninguno"
        celda.save()
        self.client.force_login(self.crear_usuario("lectura"))
        html = self.html_del_tablero()
        self.assertNotIn(_enlace("yule:index"), html)
        self.assertNotIn(_enlace("inventario:lista"), html)
        self.assertIn(_enlace("usuarios:lista"), html)  # el menú sí se pintó

    def test_un_modulo_con_url_rota_se_omite_y_no_tumba_la_pagina(self):
        """Una fila mal escrita no puede dar 500 en todas las páginas, ni al superadmin."""
        Modulo.objects.filter(clave="documentos").update(url_nombre="documentos:no_existe")
        invalidar_cache()
        with self.assertLogs("administracion.context_processors", level="WARNING") as registros:
            html = self.html_del_tablero()
        self.assertEqual(len(registros.records), 1)
        self.assertIn("documentos", registros.records[0].getMessage())
        self.assertIn(_enlace("inventario:lista"), html)
        self.assertNotIn(_enlace("documentos:lista"), html)

    def test_con_el_catalogo_vacio_la_pagina_responde(self):
        """Base sin sembrar: el tablero abre (sin módulos en el menú), no da 500."""
        Modulo.objects.all().delete()
        invalidar_cache()
        with self.assertLogs("administracion.registro", level="WARNING"):
            html = self.html_del_tablero()
        self.assertIn("Página Principal", html)
        self.assertNotIn(_enlace("inventario:lista"), html)

    def test_sin_sesion_no_hay_menu(self):
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        self.assertEqual(menu_modulos(request), {})

        self.client.logout()
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertNotIn("nav-link", html)


class TableroPorModulosTests(_BaseModulosTests):
    """Las tarjetas del tablero siguen a su módulo: apagado o sin permiso, no se ven."""

    def html_del_tablero(self):
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def test_con_todo_encendido_se_ven_las_tarjetas_de_los_tres_modulos(self):
        html = self.html_del_tablero()
        for etiqueta in ("Usuarios activos", "Total activos", "Ordenes abiertas"):
            with self.subTest(etiqueta=etiqueta):
                self.assertIn(etiqueta, html)

    def test_apagar_un_modulo_quita_su_tarjeta(self):
        self.apagar("usuarios")
        html = self.html_del_tablero()
        self.assertNotIn("Usuarios activos", html)
        self.assertIn("Total activos", html)  # las de inventario siguen
        self.assertIn("Ordenes abiertas", html)

    def test_un_rol_sin_permiso_no_ve_las_cifras_del_modulo(self):
        celda = PermisoRol.objects.get(rol__clave="lectura", modulo="usuarios")
        celda.nivel = "ninguno"
        celda.save()
        self.client.force_login(self.crear_usuario("lectura"))
        html = self.html_del_tablero()
        self.assertNotIn("Usuarios activos", html)
        self.assertIn("Total activos", html)

    def test_sin_acceso_a_inventario_y_mantenimiento_solo_queda_lo_demas(self):
        for modulo in ("inventario", "mantenimiento"):
            celda = PermisoRol.objects.get(rol__clave="lectura", modulo=modulo)
            celda.nivel = "ninguno"
            celda.save()
        self.client.force_login(self.crear_usuario("lectura"))
        html = self.html_del_tablero()
        self.assertIn("Usuarios activos", html)
        for etiqueta in ("Total activos", "Asignados", "Disponibles", "Dados de baja",
                         "Ordenes abiertas", "Les toca mantenimiento"):
            with self.subTest(etiqueta=etiqueta):
                self.assertNotIn(etiqueta, html)
