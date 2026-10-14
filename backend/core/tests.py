import tempfile
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.permisos import PERMISOS_POR_ROL
from core.views import MEDIA_PERMISOS

CustomUser = get_user_model()


def _user(rol, username=None):
    return CustomUser.objects.create_user(
        username=username or f"core_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


class DashboardTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp.url)

    def test_status_200(self):
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 200)


class MediaProtegidoTests(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.media_root = Path(self.tmpdir.name)

        # Crear archivos de prueba dentro de cada prefijo permitido
        (self.media_root / "usuarios" / "fotos").mkdir(parents=True)
        (self.media_root / "inventario" / "fotos").mkdir(parents=True)
        (self.media_root / "inventario" / "actas" / "pdf").mkdir(parents=True)
        (self.media_root / "mantenimiento" / "fotos").mkdir(parents=True)
        (self.media_root / "documentos" / "2026" / "10").mkdir(parents=True)

        (self.media_root / "usuarios" / "fotos" / "x.png").write_bytes(
            b"\x89PNG\r\n\x1a\n"  # magic PNG
        )
        (self.media_root / "inventario" / "fotos" / "a.png").write_bytes(
            b"\x89PNG\r\n\x1a\n"
        )
        (self.media_root / "documentos" / "2026" / "10" / "malicioso.html").write_text(
            "<html></html>"
        )
        (self.media_root / "otro").mkdir(parents=True, exist_ok=True)
        (self.media_root / "otro" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        self.user_tecnico = _user("tecnico", username="media_tecnico")
        self.user_lectura = _user("lectura", username="media_lectura")
        self.user_admin = _user("admin", username="media_admin")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _url(self, ruta):
        return reverse("media", kwargs={"ruta": ruta})

    def _override_media(self, accel=False):
        kw = {"MEDIA_ROOT": str(self.media_root)}
        if accel:
            kw["MEDIA_ACCEL_REDIRECT"] = True
        return override_settings(**kw)

    def test_anonimo_redirige_a_login(self):
        with self._override_media():
            resp = Client().get(self._url("usuarios/fotos/x.png"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp.url)

    def test_usuario_con_permiso_ve_imagen(self):
        client = Client()
        client.force_login(self.user_tecnico)
        with self._override_media():
            resp = client.get(self._url("inventario/fotos/a.png"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/png")
        self.assertTrue(resp["Content-Disposition"].startswith("inline"))
        resp.close()  # libera el handle del archivo antes de borrar tmpdir

    def test_usuario_sin_permiso_obtiene_404(self):
        # Todos los roles reales tienen al menos lectura en los prefijos registrados.
        # Forzamos un rol con permiso "ninguno" sobre inventario para este test.
        original = PERMISOS_POR_ROL["tecnico"]["inventario"]
        PERMISOS_POR_ROL["tecnico"]["inventario"] = "ninguno"
        try:
            client = Client()
            client.force_login(self.user_tecnico)
            with self._override_media():
                resp = client.get(self._url("inventario/fotos/a.png"))
            self.assertEqual(resp.status_code, 404)
        finally:
            PERMISOS_POR_ROL["tecnico"]["inventario"] = original

    def test_path_traversal_devuelve_404(self):
        client = Client()
        client.force_login(self.user_tecnico)
        rutas = [
            "usuarios/fotos/../../.env",
            "usuarios/fotos/..%2f..%2f.env",
            "//etc/passwd",
            "usuarios/fotos/../otro/a.png",
        ]
        for ruta in rutas:
            with self.subTest(ruta=ruta), self._override_media():
                resp = client.get(self._url(ruta))
            self.assertEqual(resp.status_code, 404, ruta)

    def test_prefijo_no_registrado_devuelve_404(self):
        client = Client()
        client.force_login(self.user_tecnico)
        with self._override_media():
            resp = client.get(self._url("otro/a.png"))
        self.assertEqual(resp.status_code, 404)

    def test_html_se_fuerza_a_descarga(self):
        client = Client()
        client.force_login(self.user_admin)
        with self._override_media():
            resp = client.get(self._url("documentos/2026/10/malicioso.html"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["Content-Disposition"].startswith("attachment"))
        resp.close()

    def test_x_accel_redirect_en_produccion(self):
        client = Client()
        client.force_login(self.user_tecnico)
        with self._override_media(accel=True):
            resp = client.get(self._url("inventario/fotos/a.png"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["X-Accel-Redirect"], "/_protegido/inventario/fotos/a.png")
        self.assertEqual(resp.content, b"")

    def test_superadmin_accede_a_cualquier_prefijo(self):
        superadmin = _user("superadmin", username="media_super")
        client = Client()
        client.force_login(superadmin)
        with self._override_media():
            resp = client.get(self._url("documentos/2026/10/malicioso.html"))
        self.assertEqual(resp.status_code, 200)
        resp.close()

    def test_todos_los_upload_to_estan_registrados(self):
        """Si se añade un nuevo FileField/ImageField sin registrar su prefijo,
        este test falla y obliga a actualizar MEDIA_PERMISOS."""
        registrados = tuple(pref for pref, _ in MEDIA_PERMISOS)

        for model in apps.get_models():
            for field in model._meta.get_fields():
                if field.get_internal_type() not in ("FileField", "ImageField"):
                    continue
                upload_to = getattr(field, "upload_to", "")
                if not isinstance(upload_to, str):
                    continue
                # Quitar placeholders de fecha (documentos/%Y/%m/ -> documentos/)
                prefijo = upload_to.split("%")[0].rstrip("/") + "/"
                self.assertTrue(
                    any(prefijo.startswith(r) for r in registrados),
                    f"{model.__name__}.{field.name} -> upload_to='{upload_to}' no está "
                    f"cubierto por MEDIA_PERMISOS (prefijo calculado: '{prefijo}')",
                )
