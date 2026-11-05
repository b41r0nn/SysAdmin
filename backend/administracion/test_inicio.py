"""Pruebas de la portada del módulo de Configuración."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from administracion.models import Modulo
from administracion.registro import invalidar_cache
from notificaciones.models import NotificacionEmail


class PortadaConfiguracionTests(TestCase):
    def setUp(self):
        # La caché de módulos sobrevive al rollback de cada prueba y
        # queryset.update() no dispara señales: se limpia antes y después.
        invalidar_cache()
        self.addCleanup(invalidar_cache)
        Usuario = get_user_model()
        self.superadmin = Usuario.objects.create_user(
            username="super_portada", password="x", rol="superadmin"
        )
        self.client.force_login(self.superadmin)

    def html_de_la_portada(self):
        resp = self.client.get(reverse("administracion:inicio"))
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def test_la_portada_responde_200_al_superadministrador(self):
        resp = self.client.get(reverse("administracion:inicio"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "administracion/inicio.html")

    def test_un_tecnico_no_entra_a_la_portada(self):
        # administracion es "ninguno" para tecnico: redirige (302), no 404.
        tecnico = get_user_model().objects.create_user(
            username="tecnico_portada", password="x", rol="tecnico"
        )
        self.client.force_login(tecnico)
        resp = self.client.get(reverse("administracion:inicio"))
        self.assertEqual(resp.status_code, 302)

    def test_un_anonimo_va_al_login(self):
        self.client.logout()
        resp = self.client.get(reverse("administracion:inicio"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_la_portada_enlaza_las_nueve_areas(self):
        html = self.html_de_la_portada()
        nombres = (
            "administracion:configuracion",
            "administracion:cuentas",
            "administracion:lista_auditoria",
            "administracion:modulos",
            "administracion:roles",
            "administracion:correo",
            "administracion:seguridad",
            "administracion:datos",
            "yule:configuracion",
        )
        for nombre in nombres:
            with self.subTest(area=nombre):
                self.assertIn(f'href="{reverse(nombre)}"', html)

    def test_el_enlace_del_sidebar_apunta_a_la_portada_no_a_la_auditoria(self):
        # Regresión del síntoma que originó el módulo: «Configuración» en el
        # menú lateral llevaba a la auditoría. Si la fila apuntara a una URL
        # que no resuelve, el menú la omitiría en silencio; por eso se exige
        # que el href ESTÉ, no solo que la página no falle.
        fila = Modulo.objects.get(clave="administracion")
        self.assertEqual(fila.url_nombre, "administracion:inicio")
        html = self.html_de_la_portada()
        portada = reverse("administracion:inicio")
        auditoria = reverse("administracion:lista_auditoria")
        self.assertIn(f'<a class="nav-link active" href="{portada}">', html)
        self.assertNotIn(f'class="nav-link " href="{auditoria}"', html)
        self.assertNotIn(f'class="nav-link active" href="{auditoria}"', html)

    def test_las_tarjetas_muestran_sus_conteos(self):
        Usuario = get_user_model()
        Usuario.objects.create_user(username="inactiva_portada", password="x", is_active=False)
        activas = Usuario.objects.filter(is_active=True).count()
        total_cuentas = Usuario.objects.count()
        self.assertGreater(total_cuentas, activas)

        Modulo.objects.filter(clave="soporte").update(activo=False)
        invalidar_cache()
        modulos_activos = Modulo.objects.filter(activo=True).count()
        total_modulos = Modulo.objects.count()
        self.assertLess(modulos_activos, total_modulos)

        html = self.html_de_la_portada()
        self.assertIn(f"{activas} activas de {total_cuentas}", html)
        self.assertIn(f"{modulos_activos} de {total_modulos} activos", html)

    def test_la_tarjeta_de_correo_cuenta_pendientes_y_con_error(self):
        NotificacionEmail.objects.create(destinatario="a@x.co", asunto="a", cuerpo="a")
        NotificacionEmail.objects.create(
            destinatario="b@x.co", asunto="b", cuerpo="b", error="535 autenticación"
        )
        NotificacionEmail.objects.create(
            destinatario="c@x.co", asunto="c", cuerpo="c", enviado=True, error="viejo"
        )
        resp = self.client.get(reverse("administracion:inicio"))
        areas = {a["clave"]: a for a in resp.context["areas"]}
        self.assertIn("2 pendientes", areas["correo"]["resumen"])
        self.assertIn("1 con error", areas["correo"]["resumen"])
