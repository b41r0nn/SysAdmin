"""Tests de atomicidad (auditoría 2026-10-14, B4)."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from inventario.models import ActaAsignacion, Activo, Asignacion, Movimiento
from usuarios.models import Usuario

CustomUser = get_user_model()


def _usuario_sistema(rol="superadmin"):
    return CustomUser.objects.create_user(
        username=f"at_{rol}_{CustomUser.objects.count()}", password="testpass123", rol=rol
    )


def _persona(doc, nombre="Ana Perez"):
    return Usuario.objects.create(
        nombre_completo=nombre,
        documento_identidad=doc,
        cargo="Analista",
        area="TI",
        correo=f"{doc}@example.com",
        estado="activo",
    )


def _activo(serial, estado="disponible"):
    return Activo.objects.create(
        serial=serial, tipo_dispositivo="escritorio", marca="HP", modelo="Elite", estado=estado
    )


class AsignarAtomicoTests(TestCase):
    def setUp(self):
        self.client.force_login(_usuario_sistema())
        self.persona = _persona("100")
        self.activo = _activo("SN-AT-001")

    def test_rollback_completo_si_falla_el_email(self):
        url = reverse("inventario:asignar", args=[self.activo.pk])
        with patch("inventario.views.movimientos.encolar_email", side_effect=RuntimeError("smtp")):
            with self.assertRaises(RuntimeError):
                self.client.post(url, {"usuario": self.persona.pk})
        self.activo.refresh_from_db()
        self.assertEqual(self.activo.estado, "disponible")
        self.assertEqual(Asignacion.objects.count(), 0)
        self.assertEqual(Movimiento.objects.count(), 0)
        self.assertEqual(ActaAsignacion.objects.count(), 0)

    def test_no_asigna_si_el_activo_ya_no_esta_disponible(self):
        Activo.objects.filter(pk=self.activo.pk).update(estado="asignado")
        url = reverse("inventario:asignar", args=[self.activo.pk])
        self.client.post(url, {"usuario": self.persona.pk})
        self.assertEqual(Asignacion.objects.count(), 0)

    def test_asignacion_exitosa_deja_todo_consistente(self):
        url = reverse("inventario:asignar", args=[self.activo.pk])
        self.client.post(url, {"usuario": self.persona.pk})
        self.activo.refresh_from_db()
        self.assertEqual(self.activo.estado, "asignado")
        self.assertEqual(Asignacion.objects.filter(activa=True).count(), 1)
        self.assertEqual(Movimiento.objects.filter(tipo="asignacion").count(), 1)
        self.assertEqual(ActaAsignacion.objects.count(), 1)


class DevolverTrasladarAtomicoTests(TestCase):
    def setUp(self):
        self.client.force_login(_usuario_sistema())
        self.ana = _persona("100", "Ana Perez")
        self.luis = _persona("200", "Luis Gomez")
        self.activo = _activo("SN-AT-002", estado="asignado")
        self.asignacion = Asignacion.objects.create(
            activo=self.activo, usuario=self.ana, fecha_asignacion="2026-01-01"
        )

    def test_devolver_rollback_si_falla_movimiento(self):
        url = reverse("inventario:devolver", args=[self.activo.pk])
        with patch("inventario.models.Movimiento.objects.create", side_effect=RuntimeError("db")):
            with self.assertRaises(RuntimeError):
                self.client.post(url, {"observaciones": "ok"})
        self.asignacion.refresh_from_db()
        self.activo.refresh_from_db()
        self.assertTrue(self.asignacion.activa)
        self.assertEqual(self.activo.estado, "asignado")

    def test_trasladar_rollback_si_falla_movimiento(self):
        url = reverse("inventario:trasladar", args=[self.activo.pk])
        with patch("inventario.models.Movimiento.objects.create", side_effect=RuntimeError("db")):
            with self.assertRaises(RuntimeError):
                self.client.post(url, {"usuario_destino": self.luis.pk, "observaciones": "x"})
        self.asignacion.refresh_from_db()
        self.assertTrue(self.asignacion.activa)
        self.assertEqual(Asignacion.objects.count(), 1)

    def test_trasladar_exitoso(self):
        url = reverse("inventario:trasladar", args=[self.activo.pk])
        self.client.post(url, {"usuario_destino": self.luis.pk, "observaciones": "x"})
        self.asignacion.refresh_from_db()
        self.assertFalse(self.asignacion.activa)
        self.assertEqual(Asignacion.objects.filter(activa=True, usuario=self.luis).count(), 1)


class NumeroInternoReintentoTests(TestCase):
    def test_reintenta_si_el_numero_choca(self):
        primero = _activo("SN-NUM-001")
        self.assertEqual(primero.numero_interno, 1000)
        # La 1ª consulta devuelve un número ya usado (carrera); la 2ª uno libre.
        with patch("inventario.models._siguiente_numero_interno", side_effect=[1000, 1001]):
            segundo = _activo("SN-NUM-002")
        self.assertEqual(segundo.numero_interno, 1001)

    def test_agota_reintentos_y_propaga(self):
        _activo("SN-NUM-003")
        with patch("inventario.models._siguiente_numero_interno", return_value=1000):
            with self.assertRaises(IntegrityError):
                _activo("SN-NUM-004")


class ImportarFilaConErrorTests(TestCase):
    def setUp(self):
        self.client.force_login(_usuario_sistema())

    def _fila(self, serial):
        return {
            "estado": "ok",
            "datos": {
                "tipo_dispositivo": "escritorio",
                "marca": "HP",
                "modelo": "Elite",
                "serial": serial,
                "estado": "disponible",
            },
        }

    def test_activos_una_fila_falla_y_las_demas_se_crean(self):
        session = self.client.session
        session["importar_activos_filas"] = [self._fila("A1"), self._fila("A2"), self._fila("A3")]
        session.save()
        original = Activo.objects.create

        def create_falla_en_a2(**kwargs):
            if kwargs.get("serial") == "A2":
                raise IntegrityError("simulado")
            return original(**kwargs)

        with patch("inventario.models.Activo.objects.create", side_effect=create_falla_en_a2):
            self.client.post(reverse("inventario:importar_confirmar"))
        self.assertEqual(sorted(Activo.objects.values_list("serial", flat=True)), ["A1", "A3"])

    def test_usuarios_una_fila_falla_y_las_demas_se_crean(self):
        def fila(doc):
            return {
                "estado": "ok",
                "datos": {
                    "nombre_completo": f"Persona {doc}",
                    "documento_identidad": doc,
                    "cargo": "X",
                    "area": "Y",
                    "correo": f"{doc}@example.com",
                    "telefono": "",
                    "estado": "activo",
                },
            }

        session = self.client.session
        session["importar_usuarios_filas"] = [fila("1"), fila("2"), fila("3")]
        session.save()
        original = Usuario.objects.create

        def create_falla_en_2(**kwargs):
            if kwargs.get("documento_identidad") == "2":
                raise IntegrityError("simulado")
            return original(**kwargs)

        with patch("usuarios.views.Usuario.objects.create", side_effect=create_falla_en_2):
            self.client.post(reverse("usuarios:importar_confirmar"))
        self.assertEqual(
            sorted(Usuario.objects.values_list("documento_identidad", flat=True)), ["1", "3"]
        )
