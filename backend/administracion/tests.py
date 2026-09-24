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
        self.client.force_login(self.usuario)
        self.assertEqual(RegistroAuditoria.objects.count(), 1)
        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, "login")
        self.assertEqual(registro.modulo, "auth")
        self.assertEqual(registro.usuario, self.usuario)

    def test_signal_logout_crea_registro(self):
        self.client.force_login(self.usuario)
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


class AdministracionCuentasTests(TestCase):
    def setUp(self):
        self.super = crear_usuario("superadmin", "sa_ctas")
        self.tech = crear_usuario("tecnico", "tec_ctas")
        self.client.force_login(self.super)

    def test_lista_cuentas_exige_permiso_administracion(self):
        self.client.force_login(self.tech)
        resp = self.client.get(reverse("administracion:cuentas"))
        self.assertRedirects(resp, reverse("core:dashboard"))

        self.client.force_login(self.super)
        resp = self.client.get(reverse("administracion:cuentas"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "sa_ctas")

    def test_crear_cuenta_genera_password_temporal(self):
        resp = self.client.post(
            reverse("administracion:crear_cuenta"),
            {"username": "nuevo_cta", "email": "nuevo@redihos.com", "rol": "tecnico"},
            follow=True,
        )
        self.assertRedirects(resp, reverse("administracion:cuentas"))
        self.assertTrue(CustomUser.objects.filter(username="nuevo_cta").exists())
        self.assertContains(resp, "Contraseña temporal")

    def test_staff_y_superuser_solo_para_superadmin(self):
        self.client.post(
            reverse("administracion:crear_cuenta"),
            {"username": "adm_cta", "email": "adm@redihos.com", "rol": "admin"},
        )
        adm = CustomUser.objects.get(username="adm_cta")
        self.assertFalse(adm.is_superuser)
        self.assertFalse(adm.is_staff)

        self.client.post(
            reverse("administracion:cambiar_rol", args=[adm.pk]), {"rol": "superadmin"}
        )
        adm.refresh_from_db()
        self.assertEqual(adm.rol, "superadmin")
        self.assertTrue(adm.is_superuser)
        self.assertTrue(adm.is_staff)

        self.client.post(
            reverse("administracion:cambiar_rol", args=[adm.pk]), {"rol": "tecnico"}
        )
        adm.refresh_from_db()
        self.assertEqual(adm.rol, "tecnico")
        self.assertFalse(adm.is_superuser)
        self.assertFalse(adm.is_staff)

    def test_toggle_desactiva_y_reactiva(self):
        cuenta = crear_usuario("tecnico", "tog_cta")
        self.client.post(reverse("administracion:toggle_cuenta", args=[cuenta.pk]))
        cuenta.refresh_from_db()
        self.assertFalse(cuenta.is_active)
        self.client.post(reverse("administracion:toggle_cuenta", args=[cuenta.pk]))
        cuenta.refresh_from_db()
        self.assertTrue(cuenta.is_active)

    def test_no_te_desactivas_a_ti_mismo(self):
        self.client.post(reverse("administracion:toggle_cuenta", args=[self.super.pk]))
        self.super.refresh_from_db()
        self.assertTrue(self.super.is_active)

    def test_cambiar_rol(self):
        cuenta = crear_usuario("tecnico", "rol_cta")
        self.client.post(reverse("administracion:cambiar_rol", args=[cuenta.pk]), {"rol": "admin"})
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.rol, "admin")
        self.assertFalse(cuenta.is_staff)

    def test_no_te_quitas_superadmin_a_ti_mismo(self):
        resp = self.client.post(
            reverse("administracion:cambiar_rol", args=[self.super.pk]), {"rol": "tecnico"}
        )
        self.super.refresh_from_db()
        self.assertEqual(self.super.rol, "superadmin")
        self.assertContains(resp, "No puedes quitarte")

    def test_resetear_password_permite_login_con_temporal(self):
        creada = crear_usuario("tecnico", "pwd_cta")
        resp = self.client.post(
            reverse("administracion:resetear_password", args=[creada.pk]), follow=True
        )
        temporal = None
        for m in resp.context["messages"]:
            texto = str(m)
            if "reiniciada" in texto:
                temporal = texto.split("Temporal: ")[1].split(" ")[0]
        self.assertIsNotNone(temporal)
        self.client.logout()
        resp = self.client.post(
            reverse("accounts:login"),
            {"username": "pwd_cta", "password": temporal},
        )
        self.assertRedirects(resp, reverse("core:dashboard"))