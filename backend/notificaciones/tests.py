from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from administracion.models import ConfiguracionSistema
from inventario.models import ActaAsignacion, Asignacion, Activo
from licencias.models import LicenciaSoftware
from mantenimiento.models import OrdenMantenimiento, ProgramacionMantenimiento
from mantenimiento.programacion import fecha_le_toca
from notificaciones.models import Notificacion, NotificacionEmail
from notificaciones.services import (
    _detectar_actas,
    _detectar_garantias,
    _detectar_licencias,
    _detectar_ocs,
    _detectar_programacion,
    encolar_email,
    generar_mantenimiento,
    generar_notificaciones,
    procesar_cola_email,
)
from usuarios.models import Usuario
from yule.models import EquipoOCS

CustomUser = get_user_model()

HOY = timezone.localdate()


def _user(rol, **kw):
    return CustomUser.objects.create_user(
        username=f"notif_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
        **kw,
    )


def _activo(serial="SN-001", **kw):
    defaults = {
        "tipo_dispositivo": "escritorio",
        "marca": "HP",
        "modelo": "Pro",
        "estado": "disponible",
    }
    defaults.update(kw)
    return Activo.objects.create(serial=serial, **defaults)


def _usuario_refs():
    return Usuario.objects.create(
        nombre_completo="Test User",
        documento_identidad="999999",
        cargo="Tecnico",
        area="TI",
        correo="t@test.com",
    )


# ──────────────────────── Model tests ────────────────────────


class NotificacionModelTests(TestCase):
    def test_default_leida_false(self):
        u = _user("tecnico")
        n = Notificacion.objects.create(
            usuario=u, tipo="aviso", titulo="Test", mensaje="m"
        )
        self.assertFalse(n.leida)

    def test_str_format(self):
        u = _user("tecnico")
        n = Notificacion.objects.create(
            usuario=u, tipo="garantia", titulo="G1", mensaje=""
        )
        self.assertIn("Garantía", str(n))
        self.assertIn(u.username, str(n))

    def test_ordering_por_fecha_desc(self):
        u = _user("tecnico")
        old = Notificacion.objects.create(usuario=u, tipo="aviso", titulo="Old")
        Notificacion.objects.create(usuario=u, tipo="aviso", titulo="New")
        Notificacion.objects.filter(pk=old.pk).update(
            fecha_creacion=timezone.now() - timedelta(days=5)
        )
        qs = list(
            Notificacion.objects.filter(usuario=u).values_list("titulo", flat=True)
        )
        self.assertEqual(qs[0], "New")


# ──────────────────────── _puede_ver ────────────────────────


class PuedeVerTests(TestCase):
    def test_superadmin_puede_ver_todo(self):
        from accounts.permisos import MODULOS

        u = _user("superadmin")
        for m in MODULOS:
            self.assertTrue(_user_puede_ver(u, m))

    def test_tecnico_no_puede_ver_passwords(self):
        u = _user("tecnico")
        self.assertFalse(_user_puede_ver(u, "passwords"))

    def test_lectura_no_puede_ver_administracion(self):
        u = _user("lectura")
        self.assertFalse(_user_puede_ver(u, "administracion"))


def _user_puede_ver(user, modulo):
    from notificaciones.services import _puede_ver

    return _puede_ver(user, modulo)


# ──────────────────────── Detectores ────────────────────────


class DetectarGarantiasTests(TestCase):
    def test_garantia_vencida_genera_notificacion(self):
        u = _user("superadmin")
        _activo(
            "SN-G1",
            fecha_compra=HOY - timedelta(days=400),
            garantia_fabrica_meses=12,
        )
        _detectar_garantias(u)
        self.assertEqual(Notificacion.objects.filter(usuario=u, tipo="garantia").count(), 1)

    def test_garantia_por_vencer_genera_notificacion(self):
        u = _user("superadmin")
        _activo(
            "SN-G2",
            fecha_compra=HOY - timedelta(days=29 * 30),
            garantia_fabrica_meses=12,
        )
        _detectar_garantias(u)
        self.assertEqual(Notificacion.objects.filter(usuario=u, tipo="garantia").count(), 1)

    def test_garantia_ok_no_genera_notificacion(self):
        u = _user("superadmin")
        _activo(
            "SN-G3",
            fecha_compra=HOY - timedelta(days=60),
            garantia_fabrica_meses=24,
        )
        _detectar_garantias(u)
        self.assertFalse(Notificacion.objects.filter(usuario=u, tipo="garantia").exists())

    def test_activo_dado_de_baja_no_genera(self):
        u = _user("superadmin")
        _activo(
            "SN-G4",
            estado="dado_de_baja",
            fecha_compra=HOY - timedelta(days=400),
            garantia_fabrica_meses=12,
        )
        _detectar_garantias(u)
        self.assertFalse(Notificacion.objects.filter(usuario=u, tipo="garantia").exists())

    def test_idempotencia(self):
        u = _user("superadmin")
        _activo(
            "SN-G5",
            fecha_compra=HOY - timedelta(days=400),
            garantia_fabrica_meses=12,
        )
        _detectar_garantias(u)
        count_after_first = Notificacion.objects.filter(usuario=u, tipo="garantia").count()
        _detectar_garantias(u)
        count_after_second = Notificacion.objects.filter(usuario=u, tipo="garantia").count()
        self.assertEqual(count_after_first, count_after_second)


def _le_toca(serial="SN-TOCA"):
    """Equipo con la garantía vencida hace un año: le toca desde que venció."""
    return _activo(serial, fecha_compra=HOY - timedelta(days=730), garantia_fabrica_meses=12)


def _avisos(user):
    return Notificacion.objects.filter(usuario=user, tipo="mantenimiento")


class DetectarProgramacionTests(TestCase):
    def test_aviso_le_toca_una_vez_por_ciclo(self):
        u = _user("superadmin")
        activo = _le_toca()
        desde = activo.fecha_vencimiento_garantia

        self.assertEqual(_detectar_programacion(u, hoy=HOY), 1)
        self.assertEqual(_detectar_programacion(u, hoy=HOY), 0)
        self.assertEqual(_detectar_programacion(u, hoy=HOY + timedelta(days=1)), 0)
        aviso = _avisos(u).get()
        self.assertEqual(aviso.titulo, "Le toca mantenimiento · SN-TOCA")
        self.assertEqual(
            aviso.mensaje,
            f"A {activo.get_tipo_dispositivo_display()} HP Pro le toca mantenimiento desde el {desde:%d/%m/%Y}.",
        )
        self.assertEqual(aviso.link, reverse("mantenimiento:inicio"))
        self.assertEqual(aviso.objetokey, f"mant:toca:{activo.pk}:{desde.isoformat()}")

        # Se hace el preventivo: el ciclo siguiente avisa otra vez, con otra clave.
        OrdenMantenimiento.objects.create(
            activo=activo, tipo="preventivo", estado="cerrada", fecha_apertura=HOY, fecha_cierre=HOY
        )
        self.assertEqual(_detectar_programacion(u, hoy=HOY + timedelta(days=30)), 0)
        siguiente = HOY + timedelta(days=400)
        self.assertEqual(_detectar_programacion(u, hoy=siguiente), 1)
        self.assertEqual(_avisos(u).count(), 2)
        nuevo_desde = fecha_le_toca(activo)
        self.assertGreater(nuevo_desde, desde)
        self.assertEqual(
            _avisos(u).exclude(pk=aviso.pk).get().objetokey, f"mant:toca:{activo.pk}:{nuevo_desde.isoformat()}"
        )

    def test_aviso_programado_manana(self):
        u = _user("superadmin")
        manana = _le_toca("SN-MANANA")
        ProgramacionMantenimiento.objects.create(activo=manana, fecha_programada=HOY + timedelta(days=1))
        pasado = _le_toca("SN-PASADO")
        ProgramacionMantenimiento.objects.create(activo=pasado, fecha_programada=HOY + timedelta(days=2))

        self.assertEqual(_detectar_programacion(u, hoy=HOY), 1)
        self.assertEqual(_detectar_programacion(u, hoy=HOY), 0)
        aviso = _avisos(u).get()
        fecha = HOY + timedelta(days=1)
        self.assertEqual(aviso.titulo, "Mañana: mantenimiento de SN-MANANA")
        self.assertIn(f"{fecha:%d/%m/%Y}", aviso.mensaje)
        self.assertEqual(aviso.link, reverse("mantenimiento:inicio"))
        self.assertEqual(aviso.objetokey, f"mant:prog:{manana.pk}:{fecha.isoformat()}")
        # Un programado no recibe además el aviso de "le toca".
        self.assertFalse(_avisos(u).filter(objetokey__startswith="mant:toca:").exists())

    def test_sin_aviso_en_garantia_ni_al_dia(self):
        u = _user("superadmin")
        _activo("SN-GARANTIA", fecha_compra=HOY - timedelta(days=30), garantia_fabrica_meses=24)
        al_dia = _le_toca("SN-AL-DIA")
        OrdenMantenimiento.objects.create(
            activo=al_dia, tipo="preventivo", estado="cerrada", fecha_apertura=HOY, fecha_cierre=HOY
        )
        # Un tipo sin checklist no entra en la programación.
        _activo("SN-MONITOR", tipo_dispositivo="monitor")

        self.assertEqual(_detectar_programacion(u, hoy=HOY), 0)
        self.assertFalse(_avisos(u).exists())

    def test_sin_permiso_de_mantenimiento_no_avisa(self):
        u = _user("tecnico")
        u.rol = "sin_rol"
        u.save(update_fields=["rol"])
        _le_toca()
        self.assertEqual(generar_mantenimiento(u), 0)
        self.assertFalse(_avisos(u).exists())


class DetectarLicenciasTests(TestCase):
    def _licencia(self, **kw):
        defaults = {"nombre": "Software Test"}
        defaults.update(kw)
        return LicenciaSoftware.objects.create(**defaults)

    def test_licencia_vencida_genera_notificacion(self):
        u = _user("superadmin")
        self._licencia(fecha_vencimiento=HOY - timedelta(days=3))
        _detectar_licencias(u)
        self.assertEqual(Notificacion.objects.filter(usuario=u, tipo="licencia").count(), 1)

    def test_licencia_por_vencer_genera_notificacion(self):
        u = _user("superadmin")
        self._licencia(fecha_vencimiento=HOY + timedelta(days=5))
        _detectar_licencias(u)
        self.assertEqual(Notificacion.objects.filter(usuario=u, tipo="licencia").count(), 1)

    def test_software_y_contrato_ambos_disparan(self):
        u = _user("superadmin")
        LicenciaSoftware.objects.create(
            nombre="Windows", tipo="volumen", fecha_vencimiento=HOY - timedelta(days=1)
        )
        LicenciaSoftware.objects.create(
            nombre="Contrato soporte HP", tipo="contrato", fecha_vencimiento=HOY + timedelta(days=3)
        )
        _detectar_licencias(u)
        self.assertEqual(Notificacion.objects.filter(usuario=u, tipo="licencia").count(), 2)

    def test_sin_vencimiento_no_genera(self):
        u = _user("superadmin")
        self._licencia()
        _detectar_licencias(u)
        self.assertFalse(Notificacion.objects.filter(usuario=u, tipo="licencia").exists())

    def test_cancelada_no_genera(self):
        u = _user("superadmin")
        self._licencia(estado="cancelada", fecha_vencimiento=HOY - timedelta(days=2))
        _detectar_licencias(u)
        self.assertFalse(Notificacion.objects.filter(usuario=u, tipo="licencia").exists())

    def test_idempotencia(self):
        u = _user("superadmin")
        self._licencia(fecha_vencimiento=HOY - timedelta(days=2))
        _detectar_licencias(u)
        c1 = Notificacion.objects.filter(usuario=u, tipo="licencia").count()
        _detectar_licencias(u)
        c2 = Notificacion.objects.filter(usuario=u, tipo="licencia").count()
        self.assertEqual(c1, c2)


class DetectarActasTests(TestCase):
    def test_acta_sin_firma_genera_notificacion(self):
        u = _user("superadmin")
        usu_ref = _usuario_refs()
        a = _activo("SN-A1")
        asig = Asignacion.objects.create(
            activo=a, usuario=usu_ref, fecha_asignacion=HOY
        )
        ActaAsignacion.objects.create(asignacion=asig)
        _detectar_actas(u)
        self.assertEqual(Notificacion.objects.filter(usuario=u, tipo="acta").count(), 1)

    def test_acta_con_firma_no_genera(self):
        u = _user("superadmin")
        usu_ref = _usuario_refs()
        a = _activo("SN-A2")
        asig = Asignacion.objects.create(
            activo=a, usuario=usu_ref, fecha_asignacion=HOY
        )
        acta = ActaAsignacion.objects.create(asignacion=asig)
        acta.escaneado_firmado = "firmado.pdf"
        acta.save(update_fields=["escaneado_firmado"])
        _detectar_actas(u)
        self.assertFalse(Notificacion.objects.filter(usuario=u, tipo="acta").exists())


class DetectarOcsTests(TestCase):
    def test_sin_vincular_genera_notificacion(self):
        u = _user("superadmin")
        EquipoOCS.objects.create(id_ocs="OCS-1", nombre_host="host1")
        _detectar_ocs(u)
        self.assertEqual(Notificacion.objects.filter(usuario=u, tipo="ocs").count(), 1)

    def test_todos_vinculados_no_genera(self):
        u = _user("superadmin")
        a = _activo("SN-O1")
        EquipoOCS.objects.create(id_ocs="OCS-2", nombre_host="host2", activo_local=a)
        _detectar_ocs(u)
        self.assertFalse(Notificacion.objects.filter(usuario=u, tipo="ocs").exists())

    def test_idempotencia(self):
        u = _user("superadmin")
        EquipoOCS.objects.create(id_ocs="OCS-3", nombre_host="host3")
        _detectar_ocs(u)
        c1 = Notificacion.objects.filter(usuario=u, tipo="ocs").count()
        _detectar_ocs(u)
        c2 = Notificacion.objects.filter(usuario=u, tipo="ocs").count()
        self.assertEqual(c1, c2)


# ──────────────────────── generar_notificaciones (rol-based) ────────────────────────


class GenerarNotificacionesTests(TestCase):
    def test_rol_admin_no_recibe_notificaciones_administracion(self):
        u = _user("admin")
        generar_notificaciones(u)
        self.assertFalse(
            Notificacion.objects.filter(usuario=u, tipo="aviso").exists()
        )

    def test_superadmin_recibe_todas_las_notificaciones(self):
        _user("superadmin")
        _activo("SN-S1", fecha_compra=HOY - timedelta(days=400), garantia_fabrica_meses=12)
        genera = _user("superadmin")
        generar_notificaciones(genera)
        self.assertTrue(Notificacion.objects.filter(usuario=genera).exists())


# ──────────────────────── Vistas ────────────────────────


class NotificacionesViewTests(TestCase):
    def setUp(self):
        self.user = _user("superadmin")
        self.client = Client()
        self.client.force_login(self.user)

    def test_lista_requiere_login(self):
        self.client.logout()
        resp = self.client.get(reverse("notificaciones:lista"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp.url)

    def test_lista_muestra_no_leidas(self):
        Notificacion.objects.create(
            usuario=self.user, tipo="aviso", titulo="Pendiente"
        )
        resp = self.client.get(reverse("notificaciones:lista"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_no_leidas"], 1)

    def test_cantidad_requiere_login(self):
        self.client.logout()
        resp = self.client.get(reverse("notificaciones:cantidad"))
        self.assertEqual(resp.status_code, 302)

    def test_cantidad_retorna_count(self):
        Notificacion.objects.create(
            usuario=self.user, tipo="aviso", titulo="P1"
        )
        Notificacion.objects.create(
            usuario=self.user, tipo="aviso", titulo="P2", leida=True
        )
        resp = self.client.get(reverse("notificaciones:cantidad"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["count"], 1)

    def test_marcar_leida_requiere_post(self):
        n = Notificacion.objects.create(
            usuario=self.user, tipo="aviso", titulo="M1"
        )
        resp = self.client.get(reverse("notificaciones:marcar_leida", args=[n.pk]))
        self.assertEqual(resp.status_code, 302)
        n.refresh_from_db()
        self.assertFalse(n.leida)

    def test_marcar_leida_post_marca(self):
        n = Notificacion.objects.create(
            usuario=self.user, tipo="aviso", titulo="M2"
        )
        resp = self.client.post(reverse("notificaciones:marcar_leida", args=[n.pk]))
        self.assertEqual(resp.status_code, 302)
        n.refresh_from_db()
        self.assertTrue(n.leida)

    def test_marcar_leida_no_notificacion_ajena(self):
        other = _user("tecnico")
        n = Notificacion.objects.create(
            usuario=other, tipo="aviso", titulo="Ajena"
        )
        resp = self.client.post(reverse("notificaciones:marcar_leida", args=[n.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_marcar_todas_requiere_post(self):
        Notificacion.objects.create(
            usuario=self.user, tipo="aviso", titulo="MT1"
        )
        resp = self.client.get(reverse("notificaciones:marcar_todas"))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Notificacion.objects.filter(usuario=self.user, leida=False).exists()
        )

    def test_marcar_todas_post(self):
        Notificacion.objects.create(
            usuario=self.user, tipo="aviso", titulo="MT2"
        )
        Notificacion.objects.create(
            usuario=self.user, tipo="aviso", titulo="MT3"
        )
        resp = self.client.post(reverse("notificaciones:marcar_todas"))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            Notificacion.objects.filter(usuario=self.user, leida=False).exists()
        )


# ─── Cola de emails ───────────────────────────────────────────────────────────


class _FakeConnection:
    def open(self):
        return True

    def close(self):
        pass

    def send_messages(self, messages):
        return len(messages)


class _FakeBrokenConnection(_FakeConnection):
    def open(self):
        raise ConnectionRefusedError("host caido")


class _FakeSendFailConnection(_FakeConnection):
    def send_messages(self, messages):
        raise OSError("smtp 554")


class EncolarEmailTests(TestCase):
    def test_crea_fila_pendiente(self):
        fila = encolar_email("a@b.co", "Asunto", "Cuerpo")
        self.assertIsNotNone(fila)
        self.assertFalse(fila.enviado)
        self.assertEqual(fila.intentos, 0)

    def test_sin_destinatario_no_crea_fila(self):
        self.assertIsNone(encolar_email("", "Asunto", "Cuerpo"))
        self.assertIsNone(encolar_email(None, "Asunto", "Cuerpo"))
        self.assertEqual(NotificacionEmail.objects.count(), 0)


class ProcesarColaEmailTests(TestCase):
    def setUp(self):
        self.config = ConfiguracionSistema.get_config()
        self.config.smtp_host = "smtp.test.com"
        self.config.smtp_puerto = 587
        self.config.smtp_usa_tls = True
        self.config.set_smtp_password("secret")
        self.config.save()

    def _sin_smtp(self):
        self.config.smtp_host = ""
        self.config.save()

    @patch("notificaciones.services.get_connection")
    def test_envia_pendientes_y_marca_enviadas(self, mock):
        encolar_email("a@b.co", "S1", "C1")
        encolar_email("a@b.co", "S2", "C2")
        mock.return_value = _FakeConnection()
        total, enviados, fallos, quedan = procesar_cola_email()
        self.assertEqual((total, enviados, fallos, quedan), (2, 2, 0, 0))
        self.assertEqual(NotificacionEmail.objects.filter(enviado=True).count(), 2)
        self.assertTrue(all(n.error == "" for n in NotificacionEmail.objects.all()))

    def test_sin_config_smtp_no_es_error(self):
        self._sin_smtp()
        encolar_email("a@b.co", "S", "C")
        self.assertEqual(procesar_cola_email(), (0, 0, 0, 0))
        self.assertEqual(NotificacionEmail.objects.filter(enviado=False).count(), 1)

    @patch("notificaciones.services.get_connection")
    def test_falla_conexion_marca_intentos_y_error_sin_reventar(self, mock):
        encolar_email("a@b.co", "S", "C")
        mock.return_value = _FakeBrokenConnection()
        total, enviados, fallos, quedan = procesar_cola_email()
        correo = NotificacionEmail.objects.get()
        self.assertEqual((total, enviados, fallos, quedan), (1, 0, 1, 1))
        self.assertEqual(correo.intentos, 1)
        self.assertIn("host caido", correo.error)
        self.assertFalse(correo.enviado)

    @patch("notificaciones.services.get_connection")
    def test_fallo_envio_incrementa_intentos_con_error(self, mock):
        encolar_email("a@b.co", "S", "C")
        mock.return_value = _FakeSendFailConnection()
        total, enviados, fallos, quedan = procesar_cola_email()
        correo = NotificacionEmail.objects.get()
        self.assertEqual((enviados, fallos), (0, 1))
        self.assertEqual(correo.intentos, 1)
        self.assertIn("smtp 554", correo.error)

    @patch("notificaciones.services.get_connection")
    def test_reenvia_tras_fallo_anterior(self, mock):
        correo = encolar_email("a@b.co", "S", "C")
        correo.intentos = 1
        correo.error = "error previo"
        correo.save()
        mock.return_value = _FakeConnection()
        total, enviados, fallos, quedan = procesar_cola_email()
        correo.refresh_from_db()
        self.assertEqual(enviados, 1)
        self.assertTrue(correo.enviado)
        self.assertEqual(correo.error, "")

    def test_llega_al_maximo_de_intentos_y_queda_en_cola(self):
        encolar_email("a@b.co", "S", "C")
        NotificacionEmail.objects.all().update(intentos=5, error="limite")
        with patch("notificaciones.services.get_connection") as mock:
            mock.return_value = _FakeConnection()
            total, enviados, fallos, quedan = procesar_cola_email()
        self.assertEqual((total, enviados, fallos, quedan), (0, 0, 0, 0))
        self.assertEqual(enviados, 0)


class GenerarNotificacionesMantenimientoCommandTests(TestCase):
    def test_comando_sin_datos_no_falla(self):
        out = StringIO()
        call_command("generar_notificaciones_mantenimiento", stdout=out)
        self.assertIn("creadas: 0", out.getvalue())

    def test_comando_genera_avisos_de_programacion(self):
        usuario = _user("superadmin")
        toca = _le_toca("SN-CMD-TOCA")
        manana = _le_toca("SN-CMD-MANANA")
        ProgramacionMantenimiento.objects.create(activo=manana, fecha_programada=HOY + timedelta(days=1))

        out = StringIO()
        call_command("generar_notificaciones_mantenimiento", stdout=out)
        self.assertIn("creadas: 2", out.getvalue())
        self.assertEqual(
            set(_avisos(usuario).values_list("objetokey", flat=True)),
            {
                f"mant:toca:{toca.pk}:{toca.fecha_vencimiento_garantia.isoformat()}",
                f"mant:prog:{manana.pk}:{(HOY + timedelta(days=1)).isoformat()}",
            },
        )

        out = StringIO()
        call_command("generar_notificaciones_mantenimiento", stdout=out)
        self.assertIn("creadas: 0", out.getvalue())
        self.assertEqual(_avisos(usuario).count(), 2)


class GenerarNotificacionesMantenimientoCommandNotificacionesTests(TestCase):
    """El comando ``generar_notificaciones_mantenimiento`` del app ``notificaciones``
    queda shadoweado por el homónimo de ``mantenimiento`` (Django resuelve por el
    primer app de INSTALLED_APPS). Se invoca el objeto Command directamente para
    cubrir su implementación."""

    def test_handle_crea_notificacion(self):
        from notificaciones.management.commands.generar_notificaciones_mantenimiento import (
            Command as Comando,
        )

        usuario = _user("superadmin")
        _le_toca("SN-HANDLE")

        comando = Comando()
        comando.stdout = StringIO()
        comando.handle()

        self.assertIn("creadas: 1", comando.stdout.getvalue())
        self.assertEqual(
            Notificacion.objects.filter(usuario=usuario, tipo="mantenimiento").count(), 1
        )


class EnviarNotificacionesEmailCommandTests(TestCase):
    def setUp(self):
        self.config = ConfiguracionSistema.get_config()
        self.config.smtp_host = "smtp.test.com"
        self.config.smtp_puerto = 587
        self.config.save()

    def test_comando_sin_cola_no_falla(self):
        out = StringIO()
        call_command("enviar_notificaciones_email", stdout=out)
        self.assertIn("0 enviados", out.getvalue())

    @patch("notificaciones.services.get_connection")
    def test_comando_envia_email_en_cola(self, mock):
        from django.core.mail import get_connection as real_get_connection

        encolar_email("a@b.co", "Asunto", "Cuerpo")

        with self.settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            mock.return_value = real_get_connection()
            out = StringIO()
            call_command("enviar_notificaciones_email", stdout=out)

        self.assertTrue(NotificacionEmail.objects.get().enviado)
        self.assertIn("1 enviados", out.getvalue())


class CampanaThrottleTests(TestCase):
    def test_campana_regenera_una_vez_por_ventana(self):
        from unittest.mock import patch

        from django.contrib.auth import get_user_model
        from django.core.cache import cache

        cache.clear()
        user = get_user_model().objects.create_user(
            username="campana_throttle", password="x", rol="superadmin"
        )
        self.client.force_login(user)
        with patch("notificaciones.views.generar_notificaciones") as gen:
            self.client.get(reverse("notificaciones:cantidad"))
            self.client.get(reverse("notificaciones:cantidad"))
        self.assertEqual(gen.call_count, 1)


class DetectarActasMantenimientoTests(TestCase):
    def _orden(self, serial="SN-AM-1", **kw):
        from mantenimiento.models import OrdenMantenimiento

        return OrdenMantenimiento.objects.create(
            activo=_activo(serial),
            tipo="preventivo",
            estado="cerrada",
            formato=2,
            fecha_cierre=HOY,
            **kw,
        )

    def test_aviso_acta_mantenimiento_sin_firmar(self):
        from notificaciones.services import _detectar_actas_mantenimiento

        u = _user("tecnico")
        orden = self._orden()
        _detectar_actas_mantenimiento(u)
        n = Notificacion.objects.get(usuario=u, tipo="mantenimiento", objetokey=f"acta_mant:{orden.pk}")
        self.assertEqual(n.titulo, f"Acta de mantenimiento sin firmar · N° {orden.pk:04d}")
        self.assertEqual(n.mensaje, "El acta del equipo SN-AM-1 aún no tiene la firma escaneada.")
        self.assertEqual(n.link, reverse("mantenimiento:detalle_orden", args=[orden.pk]))

    def test_sin_aviso_si_ya_tiene_firmada(self):
        from notificaciones.services import _detectar_actas_mantenimiento

        u = _user("tecnico")
        self._orden(acta_firmada="mantenimiento/actas/x.pdf")
        _detectar_actas_mantenimiento(u)
        self.assertFalse(Notificacion.objects.filter(usuario=u, objetokey__startswith="acta_mant:").exists())

    def test_aviso_si_esta_desactualizada(self):
        from notificaciones.services import _detectar_actas_mantenimiento, generar_mantenimiento

        u = _user("tecnico")
        orden = self._orden(acta_firmada="mantenimiento/actas/x.pdf", acta_firmada_desactualizada=True)
        generar_mantenimiento(u)
        self.assertTrue(
            Notificacion.objects.filter(usuario=u, objetokey=f"acta_mant:{orden.pk}").exists()
        )
        _detectar_actas_mantenimiento(u)
        self.assertEqual(Notificacion.objects.filter(usuario=u, objetokey=f"acta_mant:{orden.pk}").count(), 1)
