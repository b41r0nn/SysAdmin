"""Pruebas del filtro de módulos apagados (``ModuloActivoMiddleware``).

Un módulo apagado deja de existir: sus URLs responden 404, no una redirección,
y eso vale también para el superadministrador y para las páginas públicas del
módulo (el formulario de reporte de soporte, por ejemplo).
"""

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import ResolverMatch, reverse

from administracion.middleware import APPS_SIEMPRE_ABIERTAS, ModuloActivoMiddleware
from administracion.models import Modulo
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
