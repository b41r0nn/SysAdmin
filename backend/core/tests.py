import os
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.apps import apps
from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import InterfaceError, ProgrammingError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from administracion.models import Modulo, PermisoRol
from administracion.registro import invalidar_cache
from core.utils import acotado, get_client_ip
from core.views import MEDIA_PERMISOS

CustomUser = get_user_model()


def _user(rol, username=None):
    return CustomUser.objects.create_user(
        username=username or f"core_{rol}_{CustomUser.objects.count()}",
        password="x",
        rol=rol,
    )


class ClientIPTests(TestCase):
    def test_toma_ultimo_valor_de_forwarded_for(self):
        request = SimpleNamespace(META={"HTTP_X_FORWARDED_FOR": "9.9.9.9, 10.0.0.5"})
        self.assertEqual(get_client_ip(request), "10.0.0.5")

    def test_sin_forwarded_usa_remote_addr(self):
        request = SimpleNamespace(META={"REMOTE_ADDR": "192.168.1.10"})
        self.assertEqual(get_client_ip(request), "192.168.1.10")

    def test_forwarded_vacio_cae_a_remote_addr(self):
        request = SimpleNamespace(
            META={"HTTP_X_FORWARDED_FOR": "", "REMOTE_ADDR": "192.168.1.10"}
        )
        self.assertEqual(get_client_ip(request), "192.168.1.10")

    def test_request_none(self):
        self.assertIsNone(get_client_ip(None))

    def test_request_sin_meta(self):
        self.assertIsNone(get_client_ip(SimpleNamespace()))


class VaultKeyCheckTests(TestCase):
    def _run(self):
        from core.checks import check_passwords_encryption_key

        return check_passwords_encryption_key(None)

    @override_settings(PASSWORDS_ENCRYPTION_KEY="")
    def test_w001_si_falta_clave(self):
        self.assertEqual([e.id for e in self._run()], ["sysadmin.W001"])

    @override_settings(PASSWORDS_ENCRYPTION_KEY="clave-fernet-de-prueba")
    def test_sin_warning_con_clave(self):
        self.assertEqual(self._run(), [])


class ModulosSembradosCheckTests(TestCase):
    """W002: un módulo de ``MODULOS`` sin fila queda fuera de la interfaz.

    No aparece en la pantalla de módulos ni en la matriz de roles (las dos
    iteran ``Modulo.objects.all()``), así que sus permisos son ineditables.
    """

    def _run(self):
        from core.checks import check_modulos_sembrados

        return check_modulos_sembrados(None)

    def test_sin_warning_con_los_diez_sembrados(self):
        self.assertEqual(Modulo.objects.count(), 10)
        self.assertEqual(self._run(), [])

    def test_w002_si_falta_la_fila_de_un_modulo(self):
        Modulo.objects.filter(clave="soporte").delete()
        avisos = self._run()
        self.assertEqual([a.id for a in avisos], ["sysadmin.W002"])
        self.assertIn("soporte", avisos[0].msg)

    def test_con_la_base_sin_tablas_no_revienta(self):
        """El chequeo corre también antes de ``migrate``: no puede tumbar manage.py."""
        with mock.patch("administracion.models.Modulo.objects") as objetos:
            objetos.values_list.side_effect = ProgrammingError("no existe la relacion")
            self.assertEqual(self._run(), [])

    def test_con_la_conexion_cerrada_tampoco_revienta(self):
        """``InterfaceError`` hereda de ``django.db.Error``, no de ``DatabaseError``.

        Es el «connection already closed» de psycopg, así que solo muerde en
        PostgreSQL. Aquí tumbaría cualquier ``manage.py`` —incluido el
        ``migrate`` de un despliegue— en vez de una petición.
        """
        with mock.patch("administracion.models.Modulo.objects") as objetos:
            objetos.values_list.side_effect = InterfaceError("connection already closed")
            self.assertEqual(self._run(), [])


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

    def test_dashboard_muestra_equipos_que_les_toca(self):
        from inventario.models import Activo

        hoy = timezone.localdate()
        for serial in ("SN-D1", "SN-D2"):
            # Garantía vencida hace un año: le toca desde que venció.
            Activo.objects.create(
                serial=serial, tipo_dispositivo="escritorio", marca="HP", modelo="Pro",
                estado="disponible", fecha_compra=hoy - timedelta(days=730), garantia_fabrica_meses=12,
            )
        Activo.objects.create(
            serial="SN-D3", tipo_dispositivo="escritorio", marca="HP", modelo="Pro",
            estado="disponible", fecha_compra=hoy - timedelta(days=30), garantia_fabrica_meses=24,
        )
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.context["les_toca_mantenimiento"], 2)
        self.assertContains(resp, "Les toca mantenimiento")
        self.assertContains(resp, "bi-tools")
        self.assertNotContains(resp, "Ordenes atrasadas")
        self.assertNotContains(resp, "ALERTA")
        tarjeta = resp.content.decode().split("Les toca mantenimiento")[0].rsplit("sa-stat-card", 1)[1]
        self.assertIn("text-warning", tarjeta)
        self.assertNotIn("danger", tarjeta)


def _cerrar_archivo(resp):
    """Libera el handle del archivo de un FileResponse antes de borrar tmpdir.

    Consumir streaming_content deja que el wrapper del test client cierre el
    archivo con close_old_connections desconectado. resp.close() directo
    dispara request_finished y, con PostgreSQL, cierra la conexión de BD en
    mitad del TestCase.
    """
    b"".join(resp.streaming_content)


class MediaProtegidoTests(TestCase):
    def setUp(self):
        # La caché de permisos sobrevive al rollback de cada prueba.
        invalidar_cache()
        self.addCleanup(invalidar_cache)
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
        """Fija **las dos** opciones, nunca hereda `MEDIA_ACCEL_REDIRECT`.

        Es `False` en `settings/base.py` y `True` en `settings/production.py`,
        así que heredarla hacía que estas pruebas midieran un camino distinto
        según el módulo de settings: con los de producción —que es como se corre
        la suite dentro del contenedor— las tres que llaman a `_cerrar_archivo`
        caían en la rama de `X-Accel-Redirect`, donde no hay `streaming_content`,
        y reventaban con `AttributeError`. Una prueba que cambia de sujeto según
        el entorno no prueba nada: el camino se elige aquí.
        """
        return override_settings(
            MEDIA_ROOT=str(self.media_root), MEDIA_ACCEL_REDIRECT=accel,
        )

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
        _cerrar_archivo(resp)

    def test_usuario_sin_permiso_obtiene_404(self):
        # Todos los roles reales tienen al menos lectura en los prefijos
        # registrados. Dejamos al técnico en "ninguno" sobre inventario: el
        # rollback de TestCase devuelve la fila y setUp limpia la caché.
        PermisoRol.objects.filter(rol__clave="tecnico", modulo="inventario").update(
            nivel="ninguno"
        )
        invalidar_cache()
        client = Client()
        client.force_login(self.user_tecnico)
        with self._override_media():
            resp = client.get(self._url("inventario/fotos/a.png"))
        self.assertEqual(resp.status_code, 404)

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
        _cerrar_archivo(resp)

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
        _cerrar_archivo(resp)

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


class VendorAssetsTests(TestCase):
    """Los assets front (bootstrap, htmx, fullcalendar, fonts) se sirven
    localmente desde static/vendor; ninguna plantilla debe apuntar a un CDN."""

    HOSTS_CDN = (
        "cdn.jsdelivr.net",
        "unpkg.com",
        "googleapis.com",
        "gstatic.com",
        "cdnjs",
    )

    def test_plantillas_sin_cdn_externos(self):
        base = Path(settings.BASE_DIR)
        directorios = [base / "templates"]
        directorios += [d / "templates" for d in base.iterdir() if (d / "templates").is_dir()]
        encontrados = []
        for directorio in directorios:
            for plantilla in directorio.rglob("*.html"):
                contenido = plantilla.read_text(encoding="utf-8")
                for host in self.HOSTS_CDN:
                    if host in contenido:
                        encontrados.append(f"{plantilla.relative_to(base)} -> {host}")
        self.assertEqual(encontrados, [], f"Plantillas con CDN externo: {encontrados}")


class AvisoHtmxJsTests(TestCase):
    """El único aviso de un cambio por HTMX que no se guardó vive en el JS.

    Con un 4xx, HTMX no intercambia nada: el interruptor o el ``<select>`` se
    quedan mostrando el valor que el usuario acaba de poner aunque el servidor
    no haya guardado nada, y sin el manejador nadie avisa. Es una prueba de
    grep a propósito —aquí no se ejecuta JavaScript—, para que el manejador no
    desaparezca sin que nada falle.
    """

    def test_el_js_maneja_los_errores_de_htmx(self):
        fuente = (
            Path(settings.BASE_DIR) / "static" / "js" / "sysadmin.js"
        ).read_text(encoding="utf-8")
        # El manejador del error y el que recuerda el valor real del control
        # para poder devolverlo a su sitio.
        self.assertIn("htmx:responseError", fuente)
        self.assertIn("htmx:load", fuente)


class LimpiarHistorialCommandTests(TestCase):
    def test_dry_run_no_borra_nada(self):
        from administracion.models import RegistroAuditoria

        registro = RegistroAuditoria.objects.create(modulo="inventario", accion="crear")
        RegistroAuditoria.objects.all().update(fecha=timezone.now() - timedelta(days=400))

        out = StringIO()
        call_command("limpiar_historial", dias=365, dry_run=True, stdout=out)

        self.assertTrue(RegistroAuditoria.objects.filter(pk=registro.pk).exists())
        salida = out.getvalue()
        self.assertIn("simulación", salida)
        self.assertIn("Total registros afectados", salida)

    def test_borra_solo_lo_antiguo(self):
        from administracion.models import RegistroAuditoria
        from notificaciones.models import Notificacion, NotificacionEmail
        from yule.models import SincronizacionLog

        usuario = _user("superadmin")
        viejo = timezone.now() - timedelta(days=400)
        nuevo = timezone.now()

        audit_viejo = RegistroAuditoria.objects.create(modulo="inventario", accion="crear")
        audit_nuevo = RegistroAuditoria.objects.create(modulo="inventario", accion="crear")
        RegistroAuditoria.objects.filter(pk=audit_viejo.pk).update(fecha=viejo)

        sync = SincronizacionLog.objects.create()
        SincronizacionLog.objects.filter(pk=sync.pk).update(fecha_inicio=viejo)

        content_type = ContentType.objects.get_for_model(RegistroAuditoria)
        log_viejo = LogEntry.objects.create(
            user=usuario,
            content_type=content_type,
            object_id="1",
            object_repr="x",
            action_flag=1,
            action_time=viejo,
        )

        notif_vieja = Notificacion.objects.create(usuario=usuario, tipo="aviso", titulo="t", leida=True)
        Notificacion.objects.filter(pk=notif_vieja.pk).update(fecha_creacion=viejo)
        notif_nueva = Notificacion.objects.create(usuario=usuario, tipo="aviso", titulo="t", leida=True)
        Notificacion.objects.filter(pk=notif_nueva.pk).update(fecha_creacion=nuevo)

        mail_viejo = NotificacionEmail.objects.create(
            destinatario="a@b.co", asunto="s", cuerpo="c", enviado=True, fecha_enviado=viejo
        )
        mail_nuevo = NotificacionEmail.objects.create(
            destinatario="a@b.co", asunto="s2", cuerpo="c", enviado=True, fecha_enviado=nuevo
        )

        call_command("limpiar_historial", dias=365, stdout=StringIO())

        self.assertFalse(RegistroAuditoria.objects.filter(pk=audit_viejo.pk).exists())
        self.assertTrue(RegistroAuditoria.objects.filter(pk=audit_nuevo.pk).exists())
        self.assertFalse(SincronizacionLog.objects.filter(pk=sync.pk).exists())
        self.assertFalse(LogEntry.objects.filter(pk=log_viejo.pk).exists())
        self.assertFalse(Notificacion.objects.filter(pk=notif_vieja.pk).exists())
        self.assertTrue(Notificacion.objects.filter(pk=notif_nueva.pk).exists())
        self.assertFalse(NotificacionEmail.objects.filter(pk=mail_viejo.pk).exists())
        self.assertTrue(NotificacionEmail.objects.filter(pk=mail_nuevo.pk).exists())

    def test_borra_los_correos_viejos_sin_enviar(self):
        """Una fila con error era inmortal: ``enviado=False`` por definición.

        La limpieza solo purgaba ``enviado=True``, así que el texto del fallo del
        servidor —que puede repetir la credencial que le mandamos— se quedaba
        para siempre y entraba en cada respaldo.
        """
        from notificaciones.models import NotificacionEmail

        viejo = timezone.now() - timedelta(days=400)

        fallida = NotificacionEmail.objects.create(
            destinatario="a@b.co", asunto="s", cuerpo="c", intentos=5,
            error="535 5.7.8 rechazado",
        )
        NotificacionEmail.objects.filter(pk=fallida.pk).update(fecha_creacion=viejo)
        pendiente_nueva = NotificacionEmail.objects.create(
            destinatario="a@b.co", asunto="s2", cuerpo="c", error="535 de ayer",
        )

        call_command("limpiar_historial", dias=365, stdout=StringIO())

        self.assertFalse(NotificacionEmail.objects.filter(pk=fallida.pk).exists())
        self.assertTrue(NotificacionEmail.objects.filter(pk=pendiente_nueva.pk).exists())

    def test_borra_media_huerfana_y_respeta_referenciada(self):
        """Pasa `borrar_media_huerfana` porque **el borrado ya no es el
        comportamiento por defecto** (cambio deliberado del 2026-11-10, ver
        `test_por_defecto_informa_los_huerfanos_pero_no_los_borra`). Lo que esta
        prueba sigue midiendo, y es su razón de ser, es que al borrar se respeta
        lo que sí está referenciado.
        """
        from inventario.tests import crear_activo

        with tempfile.TemporaryDirectory() as tmp:
            ref_dir = Path(tmp) / "inventario" / "fotos"
            ref_dir.mkdir(parents=True)
            referenciada = ref_dir / "keep.jpg"
            referenciada.write_bytes(b"ref")
            huerfana = Path(tmp) / "orphan.jpg"
            huerfana.write_bytes(b"huerfana")

            antiguo = (timezone.now() - timedelta(days=60)).timestamp()
            os.utime(referenciada, (antiguo, antiguo))
            os.utime(huerfana, (antiguo, antiguo))

            crear_activo("SN-MEDIA-1", foto_activo="inventario/fotos/keep.jpg")

            with override_settings(MEDIA_ROOT=tmp):
                call_command(
                    "limpiar_historial", dias=365, media_dias=30,
                    borrar_media_huerfana=True, stdout=StringIO(),
                )

            self.assertTrue(referenciada.exists())
            self.assertFalse(huerfana.exists())

    # --- Las tres de abajo salieron del incidente del 2026-11-01 ---
    #
    # La limpieza semanal borró 179 archivos de `media` que SÍ estaban
    # referenciados: los PDF de Documentos, las fotos de Mantenimiento y las de
    # los usuarios. `_limpiar_media_huerfana` decidía qué era huérfano contra una
    # lista de modelos escrita a mano -- `[Activo, Movimiento, ActaAsignacion]` --
    # que cubría 3 de los 8 campos de archivo del proyecto. La prueba de arriba no
    # lo cazó porque usa `Activo`, que es justo uno de los tres de la lista.
    #
    # Y no se notó durante meses porque el corte son 30 días y hasta el 25-oct
    # todo lo de `media` era más nuevo que eso: el 1-nov el corte llegó a
    # septiembre y se llevó todo de golpe. No cambió el código, cambió el
    # calendario, así que ninguna prueba de entonces podía avisar.

    def _con_archivo_antiguo(self, tmp, ruta_rel, contenido=b"%PDF-1.4"):
        """Crea en disco un archivo con fecha anterior al corte y devuelve su Path."""
        destino = Path(tmp) / ruta_rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
        antiguo = (timezone.now() - timedelta(days=60)).timestamp()
        os.utime(destino, (antiguo, antiguo))
        return destino

    def test_no_borra_el_archivo_de_un_documento(self):
        """El caso exacto del incidente: `documentos.Documento.archivo`."""
        from documentos.models import Documento

        with tempfile.TemporaryDirectory() as tmp:
            ruta_rel = "documentos/2026/09/manual.pdf"
            archivo = self._con_archivo_antiguo(tmp, ruta_rel)
            Documento.objects.create(titulo="Manual de restauración", archivo=ruta_rel)

            with override_settings(MEDIA_ROOT=tmp):
                call_command("limpiar_historial", dias=365, media_dias=30, stdout=StringIO())

            self.assertTrue(archivo.exists(), "se borró un archivo referenciado")

    def test_no_borra_la_foto_de_un_empleado(self):
        """Otra app distinta, para no arreglar solo el caso que se reportó.

        `usuarios.Usuario` es la ficha del empleado, no la cuenta de login
        (`accounts.CustomUser`); su `foto` es otro de los cinco campos que la
        lista a mano no cubría.
        """
        from usuarios.models import Usuario

        with tempfile.TemporaryDirectory() as tmp:
            ruta_rel = "usuarios/fotos/retrato.jpg"
            archivo = self._con_archivo_antiguo(tmp, ruta_rel, b"jpg")
            Usuario.objects.create(
                nombre_completo="Empleado de prueba", documento_identidad="MEDIA-1",
                cargo="Soporte", area="Sistemas", correo="e@b.co", foto=ruta_rel,
            )

            with override_settings(MEDIA_ROOT=tmp):
                call_command("limpiar_historial", dias=365, media_dias=30, stdout=StringIO())

            self.assertTrue(archivo.exists(), "se borró un archivo referenciado")

    def test_la_limpieza_mira_todos_los_modelos_con_archivos(self):
        """La invariante que impide que esto vuelva por un campo nuevo.

        Es el equivalente, para la limpieza, de lo que
        `test_todos_los_upload_to_estan_registrados` hace con `MEDIA_PERMISOS`:
        ahí existía esa red y aquí no, y por eso el agujero duró meses. Si
        alguien vuelve a una lista escrita a mano, o añade un modelo con un
        `FileField` que la lista no contemple, esto falla.
        """
        from django.db.models import FileField

        from core.management.commands.limpiar_historial import Command

        con_archivos = {
            modelo
            for modelo in apps.get_models()
            if any(isinstance(f, FileField) for f in modelo._meta.fields)
        }
        # Si esto falla, el proyecto perdió todos sus campos de archivo y la
        # prueba ya no mide nada.
        self.assertTrue(con_archivos)
        self.assertEqual(set(Command()._modelos_con_archivos()), con_archivos)

    def test_por_defecto_informa_los_huerfanos_pero_no_los_borra(self):
        """Un barrido automático no puede destruir lo que no puede juzgar.

        Salió de la auditoría del 2026-11-10: en `media` de producción había 7
        **actas firmadas escaneadas reales** sin fila que las referenciara
        (`Joan Sebastian Diaz.pdf`, `doc00054920260413141601.pdf` de 2,9 MB…).
        Para el barrido son huérfanas por definición y las habría borrado al
        cumplir 30 días.

        El punto es que **«sin referencia» no significa «sin valor»**: un acta
        firmada cuya fila se borró sigue siendo un documento legal. Recuperar
        unos megas de disco no compensa destruir lo irreemplazable, así que por
        defecto el comando informa y no borra. Borrar sigue siendo posible, pero
        hay que pedirlo.
        """
        with tempfile.TemporaryDirectory() as tmp:
            huerfano = self._con_archivo_antiguo(tmp, "inventario/actas/viejo.pdf")
            salida = StringIO()

            with override_settings(MEDIA_ROOT=tmp):
                call_command(
                    "limpiar_historial", dias=365, media_dias=30,
                    stdout=salida, stderr=salida,
                )

            self.assertTrue(huerfano.exists(), "borró un huérfano sin que se lo pidieran")
            texto = salida.getvalue()
            self.assertIn("no se borraron", texto)
            # Y tiene que decir CUALES, o el informe no sirve para actuar.
            self.assertIn("inventario/actas/viejo.pdf", texto)

    def test_con_la_bandera_explicita_si_borra_los_huerfanos(self):
        """La capacidad no se pierde: se vuelve deliberada."""
        with tempfile.TemporaryDirectory() as tmp:
            huerfano = self._con_archivo_antiguo(tmp, "inventario/actas/viejo.pdf")

            with override_settings(MEDIA_ROOT=tmp):
                call_command(
                    "limpiar_historial", dias=365, media_dias=30,
                    borrar_media_huerfana=True, stdout=StringIO(),
                )

            self.assertFalse(huerfano.exists())

    def test_si_no_se_pueden_leer_las_referencias_no_borra_nada(self):
        """Fallar cerrado, por la misma razón que la retención.

        Si la consulta de referencias falla a medias, los archivos que no se
        alcanzaron a leer parecen huérfanos y se borran. Un huérfano que
        sobrevive cuesta disco; un archivo referenciado que se borra no se
        recupera. Ante la duda, no se borra.
        """
        from django.db.utils import DatabaseError

        from core.management.commands.limpiar_historial import Command

        with tempfile.TemporaryDirectory() as tmp:
            archivo = self._con_archivo_antiguo(tmp, "documentos/2026/09/x.pdf")
            salida = StringIO()

            with override_settings(MEDIA_ROOT=tmp), mock.patch.object(
                Command, "_archivos_referenciados",
                side_effect=DatabaseError("sin tabla"),
            ):
                call_command(
                    "limpiar_historial", dias=365, media_dias=30,
                    stdout=salida, stderr=salida,
                )

            self.assertTrue(archivo.exists(), "borró sin saber qué estaba referenciado")
            self.assertIn("no se revisó", salida.getvalue())

    def test_borra_sesiones_vencidas(self):
        # Las vistas previas de importación abandonadas viven en django_session con
        # las claves cifradas: no deben quedar para siempre (ni tras rotar la clave).
        from django.contrib.sessions.backends.db import SessionStore
        from django.contrib.sessions.models import Session

        vencida = SessionStore()
        vencida["importar_credenciales:1"] = {"nuevas": [{"secreto_cifrado": "gAAAA-ejemplo"}]}
        vencida.create()
        Session.objects.filter(pk=vencida.session_key).update(expire_date=timezone.now() - timedelta(minutes=1))
        vigente = SessionStore()
        vigente["dato"] = 1
        vigente.create()

        out = StringIO()
        call_command("limpiar_historial", dias=365, dry_run=True, stdout=out)
        self.assertIn("Sesiones vencidas: 1", out.getvalue())
        self.assertEqual(Session.objects.count(), 2)

        call_command("limpiar_historial", dias=365, stdout=StringIO())
        self.assertFalse(Session.objects.filter(pk=vencida.session_key).exists())
        self.assertTrue(Session.objects.filter(pk=vigente.session_key).exists())


class AcotadoTests(SimpleTestCase):
    """El acotado compartido por los dos resolvedores que no se fían de la base.

    Lo usan ``administracion.seguridad`` (política del login) y
    ``core.management.commands.limpiar_historial`` (retención). Vive aquí, en una
    sola función, porque lo delicado es el borde: un ``>`` donde va un ``>=``
    cambia la política sin que nada falle. El aviso se inyecta porque los dos
    tienen sinks distintos: el primero el logger y el segundo ``stderr``, que el
    cron recoge (un logger ahí dejaría el aviso dos veces).
    """

    def _avisos(self):
        avisos = []
        return avisos, avisos.append

    def test_un_valor_en_rango_pasa_intacto_y_sin_avisar(self):
        avisos, avisar = self._avisos()
        for valor in (1, 50, 100):
            self.assertEqual(acotado(valor, 1, 100, "X", avisar), valor)
        self.assertEqual(avisos, [])

    def test_los_bordes_son_validos(self):
        """El tope es el último valor aceptable, no el primero rechazado."""
        avisos, avisar = self._avisos()
        self.assertEqual(acotado(1, 1, 100, "X", avisar), 1)
        self.assertEqual(acotado(100, 1, 100, "X", avisar), 100)
        self.assertEqual(avisos, [])

    def test_por_encima_y_por_debajo_se_acota_y_se_avisa(self):
        avisos, avisar = self._avisos()
        self.assertEqual(acotado(101, 1, 100, "Los minutos", avisar), 100)
        self.assertEqual(acotado(0, 1, 100, "Los minutos", avisar), 1)
        self.assertEqual(len(avisos), 2)
        for aviso in avisos:
            self.assertIn("Los minutos", aviso)

    def test_un_none_cae_al_minimo_en_vez_de_reventar(self):
        """Comparar None con un int es TypeError, o sea el 500 que se evita."""
        avisos, avisar = self._avisos()
        self.assertEqual(acotado(None, 7, 30, "X", avisar), 7)
        self.assertEqual(len(avisos), 1)

    def test_el_aviso_no_depende_del_genero_de_la_etiqueta(self):
        """Es texto en español que se lee en el log de producción.

        Con un ``"%s guardado fuera de rango"`` salía «Los minutos de sesión
        guardado» y «Las horas de bloqueo guardado».
        """
        avisos, avisar = self._avisos()
        for etiqueta in (
            "los minutos de sesión",
            "las horas de bloqueo",
            "la longitud mínima de la contraseña",
            "el límite de intentos",
        ):
            acotado(99999, 1, 10, etiqueta, avisar)
        for aviso in avisos:
            self.assertNotIn("guardado", aviso)


class GuardarExcelTests(TestCase):
    def test_texto_con_igual_no_queda_como_formula(self):
        from io import BytesIO

        from openpyxl import Workbook, load_workbook

        from core.utils import guardar_excel

        wb = Workbook()
        wb.active.append(["=HYPERLINK(\"http://x\",\"clic\")", "normal"])
        buffer = BytesIO()
        guardar_excel(wb, buffer)
        buffer.seek(0)
        celda = load_workbook(buffer).active["A1"]
        self.assertEqual(celda.data_type, "s")
        self.assertEqual(celda.value, "=HYPERLINK(\"http://x\",\"clic\")")


class SmokeVistasTests(TestCase):
    """Abre con superadmin las páginas de solo lectura de cada módulo.

    Existe porque un import roto dentro de una vista (no en la cabecera del
    módulo) solo falla al abrir esa página: la lista de inventario estuvo rota
    en producción sin que ningún test la tocara.
    """

    RUTAS = [
        "core:dashboard",
        "usuarios:lista", "usuarios:crear", "usuarios:importar", "usuarios:importar_plantilla",
        "inventario:lista", "inventario:software_global", "inventario:crear", "inventario:etiquetas",
        "inventario:catalogo_lista", "inventario:catalogo_crear", "inventario:catalogo_json",
        "inventario:exportar_opciones", "inventario:importar", "inventario:importar_plantilla",
        "reports:index", "reports:activos_por_usuario", "reports:inventario_excel",
        "reports:movimientos_excel", "reports:usuarios_excel", "reports:costos_excel",
        "reports:mantenimiento_excel",
        "mantenimiento:inicio", "mantenimiento:lista_ordenes", "mantenimiento:calendario",
        "mantenimiento:calendario_eventos", "mantenimiento:reportar",
        "mantenimiento:crear_orden", "mantenimiento:nuevo", "mantenimiento:hoja_de_vida_buscar",
        "mantenimiento:lista_plantillas", "mantenimiento:crear_plantilla",
        "passwords:index", "passwords:vault_crear", "passwords:importar_plantilla",
        "yule:index", "yule:configuracion", "yule:equipos_lista", "yule:equipos_sin_match",
        "yule:historial",
        "documentos:lista", "documentos:crear", "documentos:categorias_lista",
        "administracion:lista_auditoria", "administracion:cuentas", "administracion:crear_cuenta",
        "administracion:configuracion", "administracion:inicio", "administracion:modulos",
        "administracion:roles", "administracion:correo", "administracion:seguridad",
        "administracion:datos",
        "notificaciones:lista", "notificaciones:cantidad",
        "soporte:lista", "soporte:reportar_publico", "soporte:excel", "soporte:crear",
        "licencias:lista", "licencias:crear", "licencias:exportar_excel",
        "prestamos:lista", "prestamos:crear",
    ]

    def setUp(self):
        # Licencias y préstamos nacen apagados y un módulo apagado responde 404
        # hasta al superadministrador. Aquí se comprueba que las páginas abren,
        # así que se encienden todas: el apagado se prueba por su cuenta en
        # administracion.test_roles.
        Modulo.objects.update(activo=True)
        invalidar_cache()  # update() no dispara señales
        self.addCleanup(invalidar_cache)

    def test_paginas_de_lectura_responden_200(self):
        from inventario.models import Activo

        user = get_user_model().objects.create_user(
            username="smoke_admin", password="x", rol="superadmin"
        )
        self.client.force_login(user)
        activo = Activo.objects.create(
            serial="SN-SMOKE", tipo_dispositivo="escritorio", marca="HP",
            modelo="X", estado="disponible",
        )
        from mantenimiento.models import OrdenMantenimiento

        orden = OrdenMantenimiento.objects.create(activo=activo, tipo="correctivo", estado="abierta")
        rutas = [(r, []) for r in self.RUTAS] + [
            ("mantenimiento:detalle_orden", [orden.pk]),
            ("mantenimiento:cerrar_orden", [orden.pk]),
            ("inventario:detalle", [activo.pk]),
            ("inventario:software", [activo.pk]),
            ("inventario:editar", [activo.pk]),
            ("inventario:asignar", [activo.pk]),
            ("inventario:qr_publico", [activo.pk]),
            ("mantenimiento:hoja_de_vida", [activo.pk]),
        ]
        for nombre, args in rutas:
            with self.subTest(ruta=nombre):
                resp = self.client.get(reverse(nombre, args=args))
                self.assertEqual(resp.status_code, 200, nombre)


class CamposFechaFormatoISOTests(TestCase):
    """<input type="date"> solo acepta AAAA-MM-DD; con LANGUAGE_CODE es-co Django
    renderiza DD/MM/AAAA si el widget no fija format, y el campo aparece vacío al editar."""

    def test_todos_los_input_date_renderizan_iso(self):
        import importlib
        from datetime import date

        from django import forms
        from django.utils import translation

        revisados = 0
        with translation.override("es-co"):
            for app in apps.get_app_configs():
                if not app.path.startswith(str(settings.BASE_DIR)):
                    continue
                try:
                    modulo = importlib.import_module(f"{app.name}.forms")
                except ModuleNotFoundError:
                    continue
                for nombre_form, form_cls in vars(modulo).items():
                    campos = getattr(form_cls, "base_fields", None)
                    if not isinstance(campos, dict):
                        continue
                    for nombre, campo in campos.items():
                        widget = campo.widget
                        if isinstance(widget, forms.DateInput) and widget.input_type == "date":
                            revisados += 1
                            with self.subTest(form=f"{app.name}.{nombre_form}", campo=nombre):
                                self.assertEqual(widget.format_value(date(2025, 3, 14)), "2025-03-14")
        self.assertGreater(revisados, 0)


class AislamientoDeLaSuiteTests(SimpleTestCase):
    """La suite no puede escribir en el `media` de la instalación donde corre.

    Salió de una auditoría del 2026-11-10: en el `media` de **producción**
    había 87 archivos `manual.pdf`, `manual_1PtyvqN.pdf`, `manual_1U0infs.pdf`…
    —los nombres con sufijo que Django inventa cuando el archivo ya existe— más
    7 en `inventario/actas/firmadas`. Son de `documentos/tests.py`,
    `mantenimiento/tests.py` y `mantenimiento/test_robustez.py`, que suben
    archivos de verdad **sin** redefinir `MEDIA_ROOT`: una copia por cada
    ejecución de la suite.

    Importa más de lo que parece porque la receta de verificación que quedó
    documentada en `GUIA_DEPLOY_PASO_A_PASO.md` manda correr la suite **dentro
    del contenedor de producción**, que es el único sitio donde se ven los
    settings de producción. O sea que el propio paso de verificación ensuciaba
    los datos que iba a verificar.

    Pedirle a cada prueba que recuerde un `override_settings` es la misma clase
    de disciplina a mano que falló con la lista de modelos de
    `limpiar_historial`: tres archivos ya se olvidaron. Así que el aislamiento
    lo pone el *runner* (`TEST_RUNNER`) para toda la suite y esto solo vigila
    que siga puesto.
    """

    def test_media_root_no_es_el_de_la_instalacion(self):
        real = Path(settings.BASE_DIR) / "media"
        self.assertNotEqual(
            Path(settings.MEDIA_ROOT).resolve(),
            real.resolve(),
            "La suite está apuntando al MEDIA_ROOT real: cualquier prueba que "
            "suba un archivo deja basura en la instalación. Falta el TEST_RUNNER "
            "que aísla MEDIA_ROOT (settings.TEST_RUNNER).",
        )

    def test_el_runner_tambien_apaga_el_accel_redirect(self):
        """La otra mitad del aislamiento, y viene de un rojo real.

        `MEDIA_ACCEL_REDIRECT` es `False` en `settings/base.py` y `True` en
        `settings/production.py`. Con `True`, `core.views.media_protegido`
        devuelve un `HttpResponse` vacío con `X-Accel-Redirect` —lo sirve nginx—
        en vez de un `FileResponse`, así que cualquier prueba que lea
        `streaming_content` revienta con `AttributeError`.

        Pasó dos veces: el 5-nov con `MediaProtegidoTests` y el 10-nov con
        `mantenimiento.test_acta_firmada` (:87), las dos **solo dentro del
        contenedor de producción**, que es el único entorno donde se ven esos
        settings. La primera se parcheó prueba por prueba; la segunda demostró
        que eso no escala. Fijarlo en el runner mata la clase entera: una prueba
        que quiera el camino de nginx lo pide explícitamente, como hace
        `test_x_accel_redirect_en_produccion`.
        """
        from core.test_runner import RunnerAislado

        runner = RunnerAislado()
        settings.MEDIA_ACCEL_REDIRECT = True  # simula los settings de producción
        try:
            runner._aislar_settings()
            self.assertIs(
                settings.MEDIA_ACCEL_REDIRECT, False,
                "el runner no apagó MEDIA_ACCEL_REDIRECT: las pruebas que leen "
                "streaming_content fallarán en producción",
            )
            self.assertNotEqual(
                Path(settings.MEDIA_ROOT).resolve(),
                (Path(settings.BASE_DIR) / "media").resolve(),
            )
            # Y tiene que devolver lo que había, no imponer False para siempre.
            runner._restaurar_settings()
            self.assertIs(settings.MEDIA_ACCEL_REDIRECT, True)
        finally:
            settings.MEDIA_ACCEL_REDIRECT = False

    def test_el_media_de_las_pruebas_existe_y_se_puede_escribir(self):
        """Si el runner lo aísla, tiene que dejarlo usable: si no, las pruebas
        que suben archivos fallarían por otra razón y se taparía el problema."""
        raiz = Path(settings.MEDIA_ROOT)
        self.assertTrue(raiz.is_dir(), f"{raiz} no existe")
        sonda = raiz / "sonda_de_escritura.tmp"
        try:
            sonda.write_bytes(b"ok")
            self.assertEqual(sonda.read_bytes(), b"ok")
        finally:
            sonda.unlink(missing_ok=True)
