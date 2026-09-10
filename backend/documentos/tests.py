from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from documentos.models import Categoria, Documento

CustomUser = get_user_model()


def _user(rol):
    return CustomUser.objects.create_user(
        username=f"docs_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


def _categoria(nombre="General"):
    return Categoria.objects.create(nombre=nombre)


def _doc(titulo="Test Doc", **kw):
    cat = kw.pop("categoria", None)
    doc = Documento(
        titulo=titulo,
        archivo=SimpleUploadedFile("test.txt", b"contenido"),
        **kw,
    )
    if cat:
        doc.categoria = cat
    doc.save()
    return doc


class DocumentosLoginTests(TestCase):
    def test_lista_requiere_login(self):
        resp = self.client.get(reverse("documentos:lista"))
        self.assertEqual(resp.status_code, 302)


class DocumentosCRUDTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_lista_returns_200(self):
        resp = self.client.get(reverse("documentos:lista"))
        self.assertEqual(resp.status_code, 200)

    def test_crear_documento(self):
        resp = self.client.post(
            reverse("documentos:crear"),
            {
                "titulo": "Manual",
                "tipo_documento": "manual",
                "archivo": SimpleUploadedFile("manual.pdf", b"%PDF-1.4"),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Documento.objects.filter(titulo="Manual").exists())

    def test_editar_documento(self):
        d = _doc()
        resp = self.client.post(
            reverse("documentos:editar", args=[d.pk]),
            {
                "titulo": "Editado",
                "tipo_documento": "general",
                "archivo": d.archivo,
            },
        )
        self.assertEqual(resp.status_code, 302)
        d.refresh_from_db()
        self.assertEqual(d.titulo, "Editado")

    def test_eliminar_documento(self):
        d = _doc()
        resp = self.client.post(reverse("documentos:eliminar", args=[d.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Documento.objects.filter(pk=d.pk).exists())


class CategoriasCRUDTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_lista_categorias(self):
        resp = self.client.get(reverse("documentos:categorias_lista"))
        self.assertEqual(resp.status_code, 200)

    def test_crear_categoria(self):
        resp = self.client.post(
            reverse("documentos:categoria_crear"),
            {"nombre": "Politica", "orden": 0},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Categoria.objects.filter(nombre="Politica").exists())

    def test_editar_categoria(self):
        c = _categoria()
        resp = self.client.post(
            reverse("documentos:categoria_editar", args=[c.pk]),
            {"nombre": "Procedimientos", "orden": 0},
        )
        self.assertEqual(resp.status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.nombre, "Procedimientos")

    def test_eliminar_categoria_vacia(self):
        c = _categoria()
        resp = self.client.post(reverse("documentos:categoria_eliminar", args=[c.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Categoria.objects.filter(pk=c.pk).exists())

    def test_eliminar_categoria_con_documentos_fallido(self):
        c = _categoria()
        _doc(categoria=c)
        resp = self.client.post(reverse("documentos:categoria_eliminar", args=[c.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Categoria.objects.filter(pk=c.pk).exists())


class DocumentosPermisosTests(TestCase):
    def test_lectura_no_puede_crear(self):
        user = _user("lectura")
        self.client.force_login(user)
        resp = self.client.get(reverse("documentos:crear"))
        self.assertEqual(resp.status_code, 302)
