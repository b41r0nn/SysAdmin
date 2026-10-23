import json
import threading
import time as reloj
from datetime import date, time, timedelta
from io import BytesIO, StringIO
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
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


# ─── Importación desde Excel: plantilla ──────────────────────────


class PlantillaImportacionTests(TestCase):
    def setUp(self):
        self.client.force_login(_user("superadmin"))

    def _descargar(self):
        from openpyxl import load_workbook
        resp = self.client.get(reverse("passwords:importar_plantilla"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("plantilla_importar_contrasenas.xlsx", resp["Content-Disposition"])
        return resp, load_workbook(BytesIO(resp.content))

    def test_hojas_encabezados_y_formato_texto(self):
        _, wb = self._descargar()
        self.assertEqual(wb.sheetnames, ["Plantilla Contraseñas", "Instrucciones"])
        ws = wb["Plantilla Contraseñas"]
        self.assertEqual([c.value for c in ws[1]], list(ENCABEZADOS))
        self.assertEqual(ws["C2"].number_format, "@")
        self.assertEqual(ws["C500"].number_format, "@")

    def test_filas_de_ejemplo_de_la_plantilla_no_se_importan(self):
        from openpyxl import load_workbook
        from passwords.importacion import leer_credenciales
        resp, _ = self._descargar()
        wb = load_workbook(BytesIO(resp.content))
        wb["Plantilla Contraseñas"].append(["Router oficina", "admin", "Clave-Real-1", "", "", "", ""])
        archivo = BytesIO()
        wb.save(archivo)
        archivo.seek(0)
        archivo.name = "plantilla.xlsx"
        filas, avisos = leer_credenciales(archivo, _vault())
        self.assertEqual([f["resultado"] for f in filas], ["error", "error", "nueva"])
        self.assertEqual(filas[0]["detalle"], "Fila de ejemplo de la plantilla: bórrala o reemplázala")
        self.assertEqual(_descifrar(filas[2]["secreto_cifrado"]), "Clave-Real-1")

    def test_admin_con_lectura_no_descarga(self):
        self.client.force_login(_user("admin"))
        resp = self.client.get(reverse("passwords:importar_plantilla"))
        self.assertRedirects(resp, reverse("core:dashboard"))


# ─── Importación desde Excel: vistas ─────────────────────────────


class ImportacionVistasTests(TestCase):
    CLAVE = "Clave-Secreta-XYZ"

    def setUp(self):
        self.client.force_login(_user("superadmin"))
        self.vault = _vault()

    def _url(self, nombre, vault=None):
        return reverse(f"passwords:{nombre}", kwargs={"vault_id": (vault or self.vault).pk})

    def _confirmar(self, vault=None, **kw):
        datos = self.client.session.get(f"importar_credenciales:{(vault or self.vault).pk}") or {}
        return self.client.post(self._url("credenciales_importar_confirmar", vault), {"lote": datos.get("lote", "")}, **kw)

    def _previsualizar(self, filas=None, vault=None, nombre="claves.xlsx"):
        filas = filas or [("Router", "admin", self.CLAVE, "192.168.1.1")]
        return self.client.post(self._url("credenciales_importar", vault), {"archivo": _xlsx(filas, nombre=nombre)})

    def test_preview_no_guarda_nada_ni_muestra_la_clave(self):
        resp = self._previsualizar()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Credencial.objects.count(), 0)
        self.assertNotContains(resp, self.CLAVE)
        self.assertContains(resp, "••••••••")
        self.assertNotIn(self.CLAVE, json.dumps(dict(self.client.session)))

    def test_confirmar_crea_credenciales_cifradas_y_registra_log(self):
        self._previsualizar()
        resp = self._confirmar()
        self.assertRedirects(resp, self._url("credenciales_lista"))
        cred = Credencial.objects.get(vault=self.vault)
        self.assertEqual(cred.get_secret(), self.CLAVE)
        self.assertEqual(cred.url, "https://192.168.1.1")
        log = AccesoLog.objects.get(vault=self.vault, accion="importacion_excel")
        self.assertEqual(log.detalle, "claves.xlsx: 1 creadas, 0 omitidas")
        self.assertNotIn(self.CLAVE, log.detalle)

    def test_confirmar_sin_preview_avisa_que_expiro(self):
        resp = self.client.post(self._url("credenciales_importar_confirmar"), follow=True)
        self.assertContains(resp, "La vista previa expiró")
        self.assertEqual(Credencial.objects.count(), 0)

    def test_confirmar_dos_veces_no_duplica(self):
        self._previsualizar()
        self._confirmar()
        self._confirmar()
        self.assertEqual(Credencial.objects.count(), 1)

    def test_no_sobrescribe_existentes(self):
        vieja = Credencial(vault=self.vault, titulo="Router", usuario="admin")
        vieja.set_secret("vieja")
        vieja.save()
        self._previsualizar()
        self._confirmar()
        self.assertEqual(Credencial.objects.count(), 1)
        vieja.refresh_from_db()
        self.assertEqual(vieja.get_secret(), "vieja")

    def test_confirmar_es_por_boveda(self):
        otra = _vault("Otra")
        self._previsualizar()
        resp = self.client.post(self._url("credenciales_importar_confirmar", otra), follow=True)
        self.assertContains(resp, "La vista previa expiró")
        self.assertEqual(Credencial.objects.count(), 0)

    def test_rechaza_archivo_que_no_es_xlsx(self):
        resp = self._previsualizar(nombre="claves.csv")
        self.assertRedirects(resp, self._url("credenciales_importar"))
        self.assertNotIn(f"importar_credenciales:{self.vault.pk}", self.client.session)

    def test_rechaza_archivo_muy_grande(self):
        with patch("passwords.importacion.MAX_BYTES", 10):
            resp = self._previsualizar()
        self.assertRedirects(resp, self._url("credenciales_importar"))
        self.assertNotIn(f"importar_credenciales:{self.vault.pk}", self.client.session)

    def test_admin_con_lectura_no_puede_importar(self):
        self.client.force_login(_user("admin"))
        self.assertRedirects(self.client.get(self._url("credenciales_importar")), reverse("core:dashboard"))

    def test_boton_importar_solo_con_escritura(self):
        url = self._url("credenciales_importar")
        self.assertContains(self.client.get(self._url("credenciales_lista")), url)
        self.client.force_login(_user("admin"))
        self.assertNotContains(self.client.get(self._url("credenciales_lista")), url)


# ─── Importación desde Excel: endurecimiento tras la revisión ────


class ImportacionEndurecimientoTests(TestCase):
    def setUp(self):
        self.vault = _vault()

    def _leer_wb(self, wb, nombre="claves.xlsx"):
        from passwords.importacion import leer_credenciales
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        buffer.name = nombre
        return leer_credenciales(buffer, self.vault)

    def _wb(self, filas, encabezados=ENCABEZADOS):
        wb = Workbook()
        ws = wb.active
        ws.append(list(encabezados))
        for fila in filas:
            ws.append(list(fila))
        return wb

    def test_excel_con_celda_fantasma_se_lee_rapido(self):
        wb = self._wb([("A", "u", "x")])
        wb.active.cell(row=1048576, column=1).number_format = "@"
        inicio = reloj.monotonic()
        filas, _ = self._leer_wb(wb)
        self.assertLess(reloj.monotonic() - inicio, 10)
        self.assertEqual([f["resultado"] for f in filas], ["nueva"])

    def test_valores_transformados_por_excel_son_error(self):
        wb = self._wb([
            ("Bool", "u1", True),
            ("Hora", "u2", time(12, 30)),
            ("Duracion", "u3", timedelta(days=1, hours=2)),
            ("Porcentaje", "u4", 0.5),
            ("Moneda", "u5", 100),
            ("Larga", "u6", 1234567890123456789),
            ("ErrorExcel", "u7", "#N/A"),
        ])
        ws = wb.active
        ws["C5"].number_format = "0%"
        ws["C6"].number_format = '"$"#,##0'
        filas, _ = self._leer_wb(wb)
        self.assertEqual([f["resultado"] for f in filas], ["error"] * 7)
        self.assertTrue(all(f["secreto_cifrado"] == "" for f in filas))
        self.assertIn("VERDADERO/FALSO", filas[0]["detalle"])
        self.assertIn("fecha u hora", filas[1]["detalle"])
        self.assertIn("fecha u hora", filas[2]["detalle"])
        self.assertIn("formato", filas[3]["detalle"])
        self.assertIn("formato", filas[4]["detalle"])
        self.assertIn("perdió dígitos", filas[5]["detalle"])
        self.assertIn("error de Excel", filas[6]["detalle"])

    def test_numero_valido_queda_nueva_con_aviso(self):
        filas, _ = self._leer_wb(self._wb([("A", "u", 123456)]))
        self.assertEqual(filas[0]["resultado"], "nueva")
        self.assertIn("número", filas[0]["detalle"])

    def test_encabezados_no_reconocidos_avisan(self):
        wb = self._wb([("Outlook", "a@x.com", "c1", "10.0.0.1", "dato")],
                      encabezados=("Servicio", "Correo electrónico", "Contraseña", "Dirección IP", "Extra"))
        filas, avisos = self._leer_wb(wb)
        self.assertEqual((filas[0]["usuario"], filas[0]["url"]), ("a@x.com", "https://10.0.0.1"))
        self.assertEqual(len(avisos), 1)
        self.assertIn("Extra", avisos[0])

    def test_alias_ampliados(self):
        wb = self._wb([("A", "u@x.com", "c", "intranet.local", "nota")],
                      encabezados=("Título", "Usuario/Correo", "Contraseñas", "Página web", "Observación"))
        filas, avisos = self._leer_wb(wb)
        self.assertEqual(avisos, [])
        f = filas[0]
        self.assertEqual((f["usuario"], f["url"], f["notas"], f["resultado"]),
                         ("u@x.com", "https://intranet.local", "nota", "nueva"))

    def test_sin_columna_usuario_avisa(self):
        filas, avisos = self._leer_wb(self._wb([("A", "c")], encabezados=("Título", "Contraseña")))
        self.assertEqual(avisos, ['No se encontró la columna "Usuario": las filas con el mismo título '
                                  'se tratarán como repetidas.'])

    def test_columnas_en_otro_orden_no_importa_nada(self):
        wb = self._wb([
            ("NAS", "admin", "https://nas.local", "Nas.Backup#7"),
            ("FW", "root", "192.168.1.1", "Fw-Clave-2024!"),
            ("Router", "admin", "http://192.168.1.254", "Rt-Clave-9"),
        ])
        filas, avisos = self._leer_wb(wb)
        self.assertTrue(any("orden" in a for a in avisos))
        self.assertEqual({f["resultado"] for f in filas}, {"error"})
        self.assertEqual({f["detalle"] for f in filas}, {"Revisa el orden de las columnas"})
        self.assertTrue(all(f["secreto_cifrado"] == "" and f["url"] == "" and f["notas"] == "" for f in filas))

    def test_url_que_no_es_direccion_se_marca_en_la_fila(self):
        filas, _ = self._leer_wb(self._wb([("A", "u", "x", "intranet de contabilidad")]))
        self.assertTrue(filas[0]["url_a_notas"])


class ImportacionVistasEndurecimientoTests(TestCase):
    def setUp(self):
        self.client.force_login(_user("superadmin"))
        self.vault = _vault()
        self.clave_sesion = f"importar_credenciales:{self.vault.pk}"

    def _url(self, nombre):
        return reverse(f"passwords:{nombre}", kwargs={"vault_id": self.vault.pk})

    def _previsualizar(self, filas):
        return self.client.post(self._url("credenciales_importar"), {"archivo": _xlsx(filas)})

    def test_confirmar_con_sesion_vieja_avisa_que_ya_se_aplico(self):
        self._previsualizar([("Router", "admin", "c1")])
        datos = dict(self.client.session[self.clave_sesion])
        self.client.post(self._url("credenciales_importar_confirmar"), {"lote": datos["lote"]})
        sesion = self.client.session
        sesion[self.clave_sesion] = datos
        sesion.save()
        resp = self.client.post(self._url("credenciales_importar_confirmar"), {"lote": datos["lote"]}, follow=True)
        self.assertContains(resp, "Esta importación ya se había aplicado")
        self.assertEqual(Credencial.objects.count(), 1)
        self.assertEqual(AccesoLog.objects.filter(accion="importacion_excel").count(), 1)

    def test_lote_distinto_no_importa(self):
        self._previsualizar([("Router", "admin", "c1")])
        resp = self.client.post(self._url("credenciales_importar_confirmar"), {"lote": "otro"}, follow=True)
        self.assertContains(resp, "La vista previa cambió")
        self.assertEqual(Credencial.objects.count(), 0)

    def test_sesion_guarda_solo_las_nuevas(self):
        self._previsualizar([("A", "u", "c1"), ("", "u", "c2"), ("A", "u", "c3")])
        datos = self.client.session[self.clave_sesion]
        self.assertEqual(sorted(datos), ["archivo", "lote", "nuevas", "total"])
        self.assertEqual((len(datos["nuevas"]), datos["total"]), (1, 3))

    def test_preview_marca_url_a_notas_sin_mostrarla(self):
        resp = self._previsualizar([("A", "u", "x", "intranet de contabilidad")])
        self.assertContains(resp, "→ Notas")
        self.assertNotContains(resp, "intranet de contabilidad")

    def test_error_de_lectura_no_deja_la_celda_en_los_logs(self):
        error = ValueError("could not convert string to float: 'Clave-Real-9!'")
        with patch("passwords.importacion.leer_credenciales", side_effect=error):
            with self.assertLogs("passwords.views", level="WARNING") as registro:
                resp = self._previsualizar([("A", "u", "x")])
        self.assertRedirects(resp, self._url("credenciales_importar"))
        self.assertNotIn("Clave-Real-9!", "\n".join(registro.output))

    def test_el_excel_subido_no_pasa_por_disco(self):
        from passwords.importacion import MAX_BYTES
        self.assertGreater(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, MAX_BYTES)


@skipUnless(connection.vendor == "postgresql", "select_for_update solo bloquea en PostgreSQL")
class ImportacionConcurrenteTests(TransactionTestCase):
    def test_dos_confirmaciones_simultaneas_no_duplican(self):
        usuario = _user("superadmin")
        vault = _vault()

        def url(nombre):
            return reverse(f"passwords:{nombre}", kwargs={"vault_id": vault.pk})

        primero = Client()
        primero.force_login(usuario)
        primero.post(url("credenciales_importar"), {"archivo": _xlsx([(f"T{i}", "u", f"c{i}") for i in range(200)])})
        lote = primero.session[f"importar_credenciales:{vault.pk}"]["lote"]
        segundo = Client()
        segundo.cookies = primero.cookies
        barrera = threading.Barrier(2)

        def confirmar(cliente):
            try:
                barrera.wait()
                cliente.post(url("credenciales_importar_confirmar"), {"lote": lote})
            finally:
                connection.close()

        hilos = [threading.Thread(target=confirmar, args=(c,)) for c in (primero, segundo)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        self.assertEqual(Credencial.objects.filter(vault=vault).count(), 200)
