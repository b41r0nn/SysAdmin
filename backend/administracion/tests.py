from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import ConfiguracionSistema, RegistroAuditoria
from .services import registrar_auditoria

CustomUser = get_user_model()


def crear_usuario(rol, username):
    return CustomUser.objects.create_user(
        username=username,
        password="testpass123",
        rol=rol,
    )


class ConfiguracionSistemaTests(TestCase):
    def test_get_config_crea_registro_por_defecto(self):
        config = ConfiguracionSistema.get_config()
        self.assertEqual(config.pk, 1)
        self.assertEqual(config.nombre_empresa, "REDIHOS S.A.S")
        self.assertEqual(ConfiguracionSistema.objects.count(), 1)

        config2 = ConfiguracionSistema.get_config()
        self.assertEqual(config2.pk, config.pk)
        self.assertEqual(ConfiguracionSistema.objects.count(), 1)

    def test_vista_configuracion_solo_superadmin(self):
        super_admin = crear_usuario("superadmin", "sa_cfg")
        admin = crear_usuario("admin", "adm_cfg")

        self.client.force_login(admin)
        response = self.client.get(reverse("administracion:configuracion"))
        self.assertRedirects(response, reverse("core:dashboard"))

        self.client.force_login(super_admin)
        response = self.client.get(reverse("administracion:configuracion"))
        self.assertEqual(response.status_code, 200)

    def test_vista_configuracion_actualiza(self):
        super_admin = crear_usuario("superadmin", "sa_cfg2")
        self.client.force_login(super_admin)

        response = self.client.post(
            reverse("administracion:configuracion"),
            {
                "nombre_empresa": "REDIHOS TEST S.A.S",
                "nit": "900123456",
                "direccion": "Cra 10 # 20-30",
                "telefono": "6015551234",
                "email_contacto": "sistemas@redihos.test",
                "pie_firma_reporte": "Departamento de TI",
            },
        )
        self.assertRedirects(response, reverse("administracion:configuracion"))

        config = ConfiguracionSistema.get_config()
        self.assertEqual(config.nombre_empresa, "REDIHOS TEST S.A.S")
        self.assertEqual(config.nit, "900123456")
        self.assertEqual(config.email_contacto, "sistemas@redihos.test")

    def test_no_autenticado_redirige_a_login(self):
        response = self.client.get(reverse("administracion:configuracion"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)


class RegistroAuditoriaTests(TestCase):
    def setUp(self):
        self.usuario = crear_usuario("superadmin", "auditor_user")

    def test_registrar_auditoria_helper(self):
        registrar_auditoria(
            usuario=self.usuario,
            modulo="usuarios",
            accion="crear",
            detalle="Creó el activo PRUEBA-1",
            ip="192.168.1.10",
        )
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.usuario, self.usuario)
        self.assertEqual(registro.modulo, "usuarios")
        self.assertEqual(registro.accion, "crear")
        self.assertEqual(registro.detalle, "Creó el activo PRUEBA-1")
        self.assertEqual(registro.ip, "192.168.1.10")

    def test_signal_login_crea_registro(self):
        self.assertEqual(RegistroAuditoria.objects.count(), 0)
        self.client.login(username="auditor_user", password="testpass123")
        self.assertEqual(RegistroAuditoria.objects.count(), 1)
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, "login")
        self.assertEqual(registro.modulo, "auth")
        self.assertEqual(registro.usuario, self.usuario)

    def test_signal_logout_crea_registro(self):
        self.client.login(username="auditor_user", password="testpass123")
        self.client.post(reverse("accounts:logout"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="logout").count(), 1)

    def test_lista_auditoria_visible_solo_superadmin(self):
        registrar_auditoria(self.usuario, "auth", "login")
        admin = crear_usuario("admin", "adm_aud_it")

        self.client.force_login(admin)
        response = self.client.get(reverse("administracion:lista_auditoria"))
        self.assertRedirects(response, reverse("core:dashboard"))

        self.client.force_login(self.usuario)
        response = self.client.get(reverse("administracion:lista_auditoria"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "login")

    def test_lista_auditoria_filtro_por_modulo(self):
        registrar_auditoria(self.usuario, "auth", "login", detalle="Sesión iniciada")
        registrar_auditoria(self.usuario, "usuarios", "crear", detalle="Alta de usuario PRUEBA")

        self.client.force_login(self.usuario)
        response = self.client.get(
            reverse("administracion:lista_auditoria"), {"modulo": "usuarios"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alta de usuario PRUEBA")
        self.assertNotContains(response, "Sesión iniciada")