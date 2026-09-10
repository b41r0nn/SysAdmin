from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from passwords.models import AccesoLog, Credencial, Vault

CustomUser = get_user_model()


def _user(rol):
    return CustomUser.objects.create_user(
        username=f"pw_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


def _vault(nombre="Vault Test", **kw):
    return Vault.objects.create(nombre=nombre, **kw)


# ─── Vault tests ───────────────────────────────────────────────────


class VaultLoginTests(TestCase):
    def test_index_requiere_login(self):
        resp = self.client.get(reverse("passwords:index"))
        self.assertEqual(resp.status_code, 302)


class VaultCRUDTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_index_returns_200(self):
        resp = self.client.get(reverse("passwords:index"))
        self.assertEqual(resp.status_code, 200)

    def test_crear_vault(self):
        resp = self.client.post(
            reverse("passwords:vault_crear"),
            {"nombre": "Nuevo Vault", "descripcion": "Test"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Vault.objects.filter(nombre="Nuevo Vault").exists())

    def test_editar_vault(self):
        v = _vault()
        resp = self.client.post(
            reverse("passwords:vault_editar", args=[v.pk]),
            {"nombre": "Editado", "descripcion": "x"},
        )
        self.assertEqual(resp.status_code, 302)
        v.refresh_from_db()
        self.assertEqual(v.nombre, "Editado")

    def test_eliminar_vault(self):
        v = _vault()
        resp = self.client.post(reverse("passwords:vault_eliminar", args=[v.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Vault.objects.filter(pk=v.pk).exists())

    def test_vault_crear_log(self):
        self.client.post(
            reverse("passwords:vault_crear"),
            {"nombre": "Con Log"},
        )
        self.assertTrue(AccesoLog.objects.filter(accion="vault_creado").exists())


# ─── Credencial tests ─────────────────────────────────────────────


class CredencialCRUDTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.vault = _vault()

    def test_lista_credenciales(self):
        resp = self.client.get(
            reverse("passwords:credenciales_lista", args=[self.vault.pk])
        )
        self.assertEqual(resp.status_code, 200)

    def test_crear_credencial_con_secreto(self):
        resp = self.client.post(
            reverse("passwords:credencial_crear", args=[self.vault.pk]),
            {
                "titulo": "AWS Root",
                "usuario": "admin",
                "secreto": "mi_password_123",
                "estado": "activa",
            },
        )
        self.assertEqual(resp.status_code, 302)
        cred = Credencial.objects.get(titulo="AWS Root")
        self.assertNotEqual(cred.secreto_encriptado, "")
        self.assertEqual(cred.get_secret(), "mi_password_123")

    def test_editar_credencial_sin_cambiar_secreto(self):
        cred = Credencial.objects.create(
            vault=self.vault,
            titulo="Original",
            creado_por=self.user,
        )
        cred.set_secret("old_secret")
        cred.save()
        resp = self.client.post(
            reverse("passwords:credencial_editar", args=[self.vault.pk, cred.pk]),
            {
                "titulo": "Cambiado",
                "usuario": "",
                "secreto": "",
                "estado": "activa",
            },
        )
        self.assertEqual(resp.status_code, 302)
        cred.refresh_from_db()
        self.assertEqual(cred.titulo, "Cambiado")
        self.assertEqual(cred.get_secret(), "old_secret")

    def test_eliminar_credencial(self):
        cred = Credencial.objects.create(
            vault=self.vault, titulo="Del", creado_por=self.user
        )
        resp = self.client.post(
            reverse("passwords:credencial_eliminar", args=[self.vault.pk, cred.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Credencial.objects.filter(pk=cred.pk).exists())


# ─── Acceso код / cifrado ──────────────────────────────────────────


class VaultAccessCodeTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_vault_con_codigo_acceso(self):
        v = _vault(nombre="Secreto", acceso_requerido=True)
        v.set_access_code("1234")
        v.save()
        self.assertTrue(v.check_access_code("1234"))
        self.assertFalse(v.check_access_code("wrong"))

    def test_vault_sin_codigo_acceso(self):
        v = _vault(nombre="Abierto", acceso_requerido=False)
        self.assertTrue(v.check_access_code(""))

    def test_ver_secreto_con_codigo_correcto(self):
        v = _vault(nombre="Locked", acceso_requerido=True)
        v.set_access_code("5678")
        v.save()
        cred = Credencial.objects.create(vault=v, titulo="C1")
        cred.set_secret("top_secret")
        cred.save()
        resp = self.client.post(
            reverse("passwords:credencial_secreto", args=[v.pk, cred.pk]),
            {"acceso_codigo": "5678"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["secreto"], "top_secret")

    def test_ver_secreto_con_codigo_incorrecto(self):
        v = _vault(nombre="Locked2", acceso_requerido=True)
        v.set_access_code("0000")
        v.save()
        cred = Credencial.objects.create(vault=v, titulo="C2")
        cred.set_secret("secret2")
        cred.save()
        resp = self.client.post(
            reverse("passwords:credencial_secreto", args=[v.pk, cred.pk]),
            {"acceso_codigo": "wrong"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["secreto"], "")


# ─── Export + Logs ─────────────────────────────────────────────────


class PasswordsExportTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.vault = _vault()

    def test_export_excel(self):
        resp = self.client.get(
            reverse("passwords:credenciales_export", args=[self.vault.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])

    def test_logs_returns_200(self):
        resp = self.client.get(reverse("passwords:logs", args=[self.vault.pk]))
        self.assertEqual(resp.status_code, 200)


class PasswordsPermisosTests(TestCase):
    def test_lectura_no_puede_crear_vault(self):
        user = _user("lectura")
        self.client.force_login(user)
        resp = self.client.get(reverse("passwords:vault_crear"))
        self.assertEqual(resp.status_code, 302)
