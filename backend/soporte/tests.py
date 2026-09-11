from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from inventario.models import Activo
from mantenimiento.models import OrdenMantenimiento
from notificaciones.models import Notificacion, NotificacionEmail
from soporte.models import Ticket
from soporte.views import _aviso_email_ticket

CustomUser = get_user_model()


def _user(rol):
    return CustomUser.objects.create_user(
        username=f"sopo_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


def _activo(serial="SN-SOP-001"):
    return Activo.objects.create(
        serial=serial,
        tipo_dispositivo="escritorio",
        marca="HP",
        modelo="Pro",
        estado="disponible",
    )


def _ticket(solicitante, **kw):
    defaults = {"asunto": "Monitor no enciende", "prioridad": "media"}
    defaults.update(kw)
    return Ticket.objects.create(solicitante=solicitante, **defaults)


# ─── Acceso ────────────────────────────────────────────────────────


class TicketsLoginTests(TestCase):
    def test_lista_requiere_login(self):
        resp = self.client.get(reverse("soporte:lista"))
        self.assertEqual(resp.status_code, 302)

    def test_crear_requiere_login(self):
        resp = self.client.get(reverse("soporte:crear"))
        self.assertEqual(resp.status_code, 302)


# ─── CRUD ──────────────────────────────────────────────────────────


class TicketsCRUDTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_lista_returns_200(self):
        resp = self.client.get(reverse("soporte:lista"))
        self.assertEqual(resp.status_code, 200)

    def test_crear_ticket_post(self):
        resp = self.client.post(
            reverse("soporte:crear"),
            {
                "asunto": "No abre el sistema",
                "prioridad": "alta",
                "descripcion": "Error al iniciar sesion",
            },
        )
        self.assertEqual(resp.status_code, 302)
        ticket = Ticket.objects.get(asunto="No abre el sistema")
        self.assertEqual(ticket.solicitante, self.user)
        self.assertEqual(ticket.estado, "abierto")

    def test_editar_ticket(self):
        ticket = _ticket(self.user)
        resp = self.client.post(
            reverse("soporte:editar", args=[ticket.pk]),
            {"asunto": "Asunto nuevo", "prioridad": "baja", "descripcion": "Actualizado"},
        )
        self.assertEqual(resp.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.asunto, "Asunto nuevo")
        self.assertEqual(ticket.prioridad, "baja")

    def test_detalle_returns_200(self):
        ticket = _ticket(self.user)
        resp = self.client.get(reverse("soporte:detalle", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 200)


# ─── Permisos por rol ──────────────────────────────────────────────


class TicketsPermisosTests(TestCase):
    def setUp(self):
        self.user = _user("lectura")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()

    def test_lectura_puede_ver_lista(self):
        resp = self.client.get(reverse("soporte:lista"))
        self.assertEqual(resp.status_code, 200)

    def test_lectura_puede_crear_ticket(self):
        resp = self.client.get(reverse("soporte:crear"))
        self.assertEqual(resp.status_code, 200)

    def test_lectura_no_puede_asignar(self):
        ticket = _ticket(self.user)
        resp = self.client.post(reverse("soporte:asignar", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_lectura_no_puede_escalar(self):
        ticket = _ticket(self.user)
        resp = self.client.get(reverse("soporte:escalar", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 302)


# ─── Asignacion y notificacion ─────────────────────────────────────


class AsignacionNotificacionTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.tecnico = _user("tecnico")
        self.ticket = _ticket(self.user)

    def test_asignar_notifica_al_tecnico(self):
        resp = self.client.post(
            reverse("soporte:asignar", args=[self.ticket.pk]),
            {"asignado_a": self.tecnico.pk},
        )
        self.assertEqual(resp.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.asignado_a, self.tecnico)
        self.assertEqual(self.ticket.estado, "en_proceso")
        n = Notificacion.objects.filter(
            usuario=self.tecnico,
            tipo="aviso",
            objetokey=f"ticket:{self.ticket.pk}",
        )
        self.assertEqual(n.count(), 1)

    def test_reasignar_no_duplica_notificacion(self):
        self.client.post(
            reverse("soporte:asignar", args=[self.ticket.pk]),
            {"asignado_a": self.tecnico.pk},
        )
        self.client.post(
            reverse("soporte:asignar", args=[self.ticket.pk]),
            {"asignado_a": self.tecnico.pk},
        )
        n = Notificacion.objects.filter(
            usuario=self.tecnico,
            tipo="aviso",
            objetokey=f"ticket:{self.ticket.pk}",
        )
        self.assertEqual(n.count(), 1)


# ─── Escalamiento a orden de mantenimiento ─────────────────────────


class EscalarTicketTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.activo = _activo()
        self.ticket = _ticket(self.user, prioridad="alta")

    def test_escalar_crea_orden_con_ticket(self):
        resp = self.client.post(
            reverse("soporte:escalar", args=[self.ticket.pk]),
            {
                "activo": self.activo.pk,
                "prioridad": "alta",
                "tecnico_asignado": "Carlos",
            },
        )
        self.assertEqual(resp.status_code, 302)
        orden = OrdenMantenimiento.objects.get(ticket=self.ticket)
        self.assertEqual(orden.activo, self.activo)
        self.assertEqual(orden.tipo, "correctivo")
        self.assertEqual(orden.estado, "abierta")
        self.assertEqual(orden.prioridad, "alta")
        self.assertIn(f"#{self.ticket.pk}", orden.descripcion)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.estado, "escalado")

    def test_escalar_no_duplica_orden(self):
        self.client.post(
            reverse("soporte:escalar", args=[self.ticket.pk]),
            {"activo": self.activo.pk, "prioridad": "media"},
        )
        resp = self.client.post(
            reverse("soporte:escalar", args=[self.ticket.pk]),
            {"activo": self.activo.pk, "prioridad": "media"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(OrdenMantenimiento.objects.filter(ticket=self.ticket).count(), 1)


# ─── Avisos por email en cambios de estado ─────────────────────────


class TicketEmailTriggersTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)
        self.tecnico = _user("tecnico")
        self.ticket = _ticket(self.user)

    @patch("soporte.views.encolar_email")
    def test_asignar_encola_email(self, mock):
        resp = self.client.post(
            reverse("soporte:asignar", args=[self.ticket.pk]),
            {"asignado_a": self.tecnico.pk},
        )
        self.assertEqual(resp.status_code, 302)
        mock.assert_called_once()
        args, _ = mock.call_args
        self.assertEqual(args[0], self.ticket.solicitante.email)

    @patch("soporte.views.encolar_email")
    def test_cambiar_estado_encola_email(self, mock):
        resp = self.client.post(
            reverse("soporte:cambiar_estado", args=[self.ticket.pk]),
            {"estado": "en_proceso"},
        )
        self.assertEqual(resp.status_code, 302)
        mock.assert_called_once()
        args, _ = mock.call_args
        self.assertEqual(args[0], self.ticket.solicitante.email)

    @patch("soporte.views.encolar_email")
    def test_cambiar_al_mismo_estado_no_reenvia(self, mock):
        self.ticket.estado = "en_proceso"
        self.ticket.save(update_fields=["estado"])
        resp = self.client.post(
            reverse("soporte:cambiar_estado", args=[self.ticket.pk]),
            {"estado": "en_proceso"},
        )
        self.assertEqual(resp.status_code, 302)
        mock.assert_not_called()

    def test_aviso_email_sin_email_no_rompe(self):
        self.user.email = ""
        self.user.save(update_fields=["email"])
        self.ticket.solicitante = self.user
        self.ticket.save(update_fields=["solicitante"])
        _aviso_email_ticket(self.ticket, "en_proceso")
        self.assertEqual(NotificacionEmail.objects.count(), 0)