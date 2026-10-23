from datetime import date
from io import BytesIO, StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from openpyxl import Workbook

from passwords.crypto import build_fernet
from passwords.models import AccesoLog, Credencial, Vault

CustomUser = get_user_model()

ENCABEZADOS = ("Título", "Usuario", "Contraseña", "URL", "Notas", "Estado", "Fecha de expiración")


def _xlsx(filas, encabezados=ENCABEZADOS, nombre="claves.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.append(list(encabezados))
    for fila in filas:
        ws.append(list(fila))
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    buffer.name = nombre
    return buffer


def _descifrar(token):
    return build_fernet().decrypt(token.encode()).decode()


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


class SecretoPermisosTests(TestCase):
    """Ver secretos en claro: solo superadmin/admin, con límite de intentos."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.vault = _vault(nombre="Restringido", acceso_requerido=True)
        self.vault.set_access_code("1111")
        self.vault.save()
        self.cred = Credencial.objects.create(vault=self.vault, titulo="C")
        self.cred.set_secret("s3creto")
        self.cred.save()
        self.url = reverse("passwords:credencial_secreto", args=[self.vault.pk, self.cred.pk])

    def test_rol_lectura_no_puede_ver_secreto(self):
        self.client.force_login(_user("lectura"))
        resp = self.client.post(self.url, {"acceso_codigo": "1111"})
        self.assertRedirects(
            resp, reverse("passwords:credenciales_lista", args=[self.vault.pk])
        )
        self.assertFalse(AccesoLog.objects.filter(accion="secreto_visto").exists())

    def test_rol_lectura_no_ve_boton_de_secreto(self):
        self.client.force_login(_user("lectura"))
        resp = self.client.get(reverse("passwords:credenciales_lista", args=[self.vault.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, self.url)

    def test_admin_puede_ver_secreto(self):
        self.client.force_login(_user("admin"))
        resp = self.client.post(self.url, {"acceso_codigo": "1111"})
        self.assertEqual(resp.context["secreto"], "s3creto")

    def test_codigo_invalido_queda_registrado(self):
        self.client.force_login(_user("superadmin"))
        self.client.post(self.url, {"acceso_codigo": "mal"})
        self.assertTrue(AccesoLog.objects.filter(accion="codigo_invalido").exists())

    def test_bloqueo_tras_intentos_fallidos(self):
        from passwords.views import MAX_INTENTOS_CODIGO

        self.client.force_login(_user("superadmin"))
        for _ in range(MAX_INTENTOS_CODIGO):
            self.client.post(self.url, {"acceso_codigo": "mal"})
        resp = self.client.post(self.url, {"acceso_codigo": "1111"})
        self.assertEqual(resp.context["secreto"], "")


class RotarClaveVaultTests(TestCase):
    def test_rota_secretos_legados_a_la_clave_nueva(self):
        from cryptography.fernet import Fernet
        from django.core.management import call_command
        from django.test import override_settings

        vault = _vault()
        cred = Credencial(vault=vault, titulo="Legado")
        with override_settings(PASSWORDS_ENCRYPTION_KEY=""):
            cred.set_secret("viejo")
            cred.save()

        clave = Fernet.generate_key().decode()
        with override_settings(PASSWORDS_ENCRYPTION_KEY=clave):
            # Con la clave nueva todavía se lee lo legado.
            self.assertEqual(Credencial.objects.get(pk=cred.pk).get_secret(), "viejo")
            call_command("rotar_clave_vault", stdout=StringIO())
            token = Credencial.objects.get(pk=cred.pk).secreto_encriptado
            self.assertEqual(Fernet(clave).decrypt(token.encode()).decode(), "viejo")


class SecretoIlegibleTests(TestCase):
    def test_secreto_con_clave_desconocida_no_da_500(self):
        from cryptography.fernet import Fernet

        vault = _vault()
        cred = Credencial.objects.create(
            vault=vault,
            titulo="Vieja",
            secreto_encriptado=Fernet(Fernet.generate_key()).encrypt(b"x").decode(),
        )
        self.client.force_login(_user("superadmin"))
        resp = self.client.post(
            reverse("passwords:credencial_secreto", args=[vault.pk, cred.pk]), {}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["secreto"], "")
        self.assertTrue(AccesoLog.objects.filter(accion="secreto_ilegible").exists())


# ─── Importación desde Excel: lectura y validación ───────────────


class ImportacionLecturaTests(TestCase):
    def setUp(self):
        self.vault = _vault()

    def _leer(self, filas, **kw):
        from passwords.importacion import leer_credenciales
        return leer_credenciales(_xlsx(filas, **kw), self.vault)

    def test_fila_valida_queda_nueva_y_cifrada(self):
        filas, avisos = self._leer([("Router", "admin", "S3creta!", "192.168.1.1", "", "", "")])
        self.assertEqual(avisos, [])
        f = filas[0]
        self.assertEqual((f["fila"], f["resultado"], f["estado"]), (2, "nueva", "activa"))
        self.assertEqual(f["url"], "https://192.168.1.1")
        self.assertNotIn("S3creta!", f["secreto_cifrado"])
        self.assertEqual(_descifrar(f["secreto_cifrado"]), "S3creta!")

    def test_falta_titulo_o_contrasena_es_error(self):
        filas, _ = self._leer([("", "u", "x"), ("T", "u", "")])
        self.assertEqual([f["resultado"] for f in filas], ["error", "error"])
        self.assertEqual(filas[0]["detalle"], "Falta el título")
        self.assertEqual(filas[1]["detalle"], "Falta la contraseña")
        self.assertEqual(filas[1]["secreto_cifrado"], "")

    def test_ya_existe_en_la_boveda_por_titulo_y_usuario_sin_mayusculas(self):
        Credencial.objects.create(vault=self.vault, titulo="Router", usuario="Admin")
        filas, _ = self._leer([(" router ", "admin", "x")])
        self.assertEqual(filas[0]["resultado"], "ya_existe")
        self.assertEqual(filas[0]["secreto_cifrado"], "")
        from passwords.importacion import leer_credenciales
        otra, _ = leer_credenciales(_xlsx([(" router ", "admin", "x")]), _vault("Otra"))
        self.assertEqual(otra[0]["resultado"], "nueva")

    def test_repetida_dentro_del_archivo(self):
        filas, _ = self._leer([("Router", "admin", "a"), ("ROUTER", "Admin ", "b")])
        self.assertEqual([f["resultado"] for f in filas], ["nueva", "repetida"])
        self.assertEqual(filas[1]["detalle"], "Repetida en el archivo")

    def test_encabezados_alternativos(self):
        filas, avisos = self._leer([("NAS", "root", "x", "nas.local")], encabezados=("Nombre", "User", "Clave", "Sitio"))
        self.assertEqual(avisos, [])
        self.assertEqual((filas[0]["titulo"], filas[0]["usuario"], filas[0]["resultado"]), ("NAS", "root", "nueva"))

    def test_clave_numerica_no_pierde_formato(self):
        filas, _ = self._leer([("A", "u1", 123456), ("B", "u2", 123456.0)])
        self.assertEqual([_descifrar(f["secreto_cifrado"]) for f in filas], ["123456", "123456"])

    def test_clave_convertida_en_fecha_es_error(self):
        filas, _ = self._leer([("A", "u", date(2024, 2, 1))])
        self.assertEqual(filas[0]["resultado"], "error")
        self.assertIn("fecha", filas[0]["detalle"])

    def test_estado_y_fecha(self):
        filas, _ = self._leer([
            ("A", "u1", "x", "", "", "Revocada", "31/12/2027"),
            ("B", "u2", "x", "", "", "Bloqueada", ""),
            ("C", "u3", "x", "", "", "", "31-31-2027"),
            ("D", "u4", "x", "", "", "expirada", date(2027, 1, 15)),
        ])
        self.assertEqual((filas[0]["estado"], filas[0]["fecha_expiracion"]), ("revocada", "2027-12-31"))
        self.assertEqual(filas[1]["resultado"], "error")
        self.assertIn("Estado no válido", filas[1]["detalle"])
        self.assertEqual(filas[2]["resultado"], "error")
        self.assertIn("Fecha de expiración no válida", filas[2]["detalle"])
        self.assertEqual((filas[3]["estado"], filas[3]["fecha_expiracion"]), ("expirada", "2027-01-15"))

    def test_url_invalida_va_a_notas(self):
        filas, _ = self._leer([("A", "u", "x", "intranet de contabilidad", "Nota previa")])
        self.assertEqual(filas[0]["resultado"], "nueva")
        self.assertEqual(filas[0]["url"], "")
        self.assertEqual(filas[0]["notas"], "Nota previa\nSitio: intranet de contabilidad")

    def test_columna_contrasena_faltante_advierte(self):
        filas, avisos = self._leer([("A", "u")], encabezados=("Título", "Usuario"))
        self.assertEqual(avisos, ['No se encontró la columna "Contraseña".'])
        self.assertEqual(filas[0]["resultado"], "error")

    def test_filas_vacias_se_omiten_y_hay_limite(self):
        filas, _ = self._leer([("A", "u", "x"), (None, None, None), ("B", "u", "y")])
        self.assertEqual([f["fila"] for f in filas], [2, 4])
        from passwords.importacion import ArchivoInvalido
        with patch("passwords.importacion.MAX_FILAS", 1):
            with self.assertRaises(ArchivoInvalido):
                self._leer([("A", "u", "x"), ("B", "u", "y")])

    def test_contrasena_conserva_espacios(self):
        filas, _ = self._leer([("A", "u", " a b ")])
        self.assertEqual(_descifrar(filas[0]["secreto_cifrado"]), " a b ")

    def test_titulo_muy_largo_es_error(self):
        filas, _ = self._leer([("T" * 151, "u", "x")])
        self.assertEqual(filas[0]["detalle"], "El título supera 150 caracteres")

    def test_resumen(self):
        from passwords.importacion import resumen
        filas = [{"resultado": r} for r in ("nueva", "nueva", "ya_existe", "repetida", "error")]
        self.assertEqual(resumen(filas), {"nuevas": 2, "ya_existen": 2, "errores": 1, "total": 5})
