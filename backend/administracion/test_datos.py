"""Pruebas de la pantalla de Datos: retención del historial y simulación.

La prueba que de verdad importa aquí no es ninguna de las del formulario, es
``CronDeLimpiezaTests``: mide el **efecto** y no la función.

El riesgo de esta tarea es que la pantalla nazca muerta. El comando lee la
configuración solo cuando el argumento llega en ``None``, y el cron instalado en
el servidor pasaba ``--dias 365 --media-dias 30`` de forma explícita: con esas
dos cosas juntas el administrador podía poner 90 días aquí y la limpieza
semanal —la única que corre de verdad— seguiría usando 365 para siempre. Ya
pasó algo igual en este plan con un *middleware* que existía, estaba bien
registrado y no se llamaba nunca; lo cazó una prueba que miraba el efecto.

Por eso aquí se afirma, sobre el archivo real del cron, que la línea
programada **no** pasa ninguno de los dos argumentos.
"""

import os
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from axes.models import AccessAttempt, AccessAttemptExpiration, AccessFailureLog, AccessLog
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.management.commands.limpiar_historial import AVISO_SIN_RETENCION

from .models import (
    RETENCION_DIAS_MAXIMO,
    RETENCION_DIAS_MINIMO,
    RETENCION_MEDIA_DIAS_MAXIMO,
    RETENCION_MEDIA_DIAS_MINIMO,
    ConfiguracionSistema,
    RegistroAuditoria,
)

# El valor que escribe de verdad quien cree que el campo es otra unidad. Con él
# en «Días de historial», el `timezone.now() - timedelta(days=...)` del comando
# lanza OverflowError y la limpieza semanal no purga nada nunca.
VALOR_ABSURDO = 999999999


def _cuenta(rol, username):
    return get_user_model().objects.create_user(
        username=username, password="clavelargadeseguridad", rol=rol,
    )


def _configurar_retencion(dias=None, media_dias=None):
    """Escribe la retención con ``update()`` y devuelve la fila.

    ``get_config()`` va primero a propósito: en una base de pruebas la fila
    pk=1 todavía no existe, así que un ``filter(pk=1).update(...)`` a secas
    tocaría cero filas y la prueba no afirmaría nada.

    El ``update()`` en vez de ``save()`` tampoco es casual: deja la fila
    cambiada en la base sin que ninguna instancia en memoria la delate, que es
    la única manera de comprobar que el comando la lee de verdad.
    """
    config = ConfiguracionSistema.get_config()
    cambios = {}
    if dias is not None:
        cambios["retencion_dias"] = dias
    if media_dias is not None:
        cambios["retencion_media_dias"] = media_dias
    if cambios:
        ConfiguracionSistema.objects.filter(pk=config.pk).update(**cambios)
    return ConfiguracionSistema.objects.get(pk=config.pk)


def _auditoria_de(dias):
    """Un ``RegistroAuditoria`` con fecha de hace ``dias`` días."""
    registro = RegistroAuditoria.objects.create(modulo="inventario", accion="crear")
    RegistroAuditoria.objects.filter(pk=registro.pk).update(
        fecha=timezone.now() - timedelta(days=dias),
    )
    return registro


def _limpiar(**opciones):
    """Corre el comando sin tocar el disco de media y devuelve su salida."""
    salida = StringIO()
    opciones.setdefault("sin_media", True)
    call_command("limpiar_historial", stdout=salida, stderr=salida, **opciones)
    return salida.getvalue()


class RetencionDelComandoTests(TestCase):
    """El comando sin argumentos tiene que usar lo que diga la pantalla."""

    def test_el_comando_sin_argumentos_usa_la_configuracion(self):
        _configurar_retencion(dias=90)
        viejo = _auditoria_de(120)
        nuevo = _auditoria_de(60)

        _limpiar()

        self.assertFalse(RegistroAuditoria.objects.filter(pk=viejo.pk).exists())
        self.assertTrue(RegistroAuditoria.objects.filter(pk=nuevo.pk).exists())

    def test_un_argumento_explicito_le_gana_a_la_configuracion(self):
        """Un humano depurando tiene que poder forzar un valor."""
        _configurar_retencion(dias=90)
        registro = _auditoria_de(400)

        _limpiar(dias=500)

        self.assertTrue(RegistroAuditoria.objects.filter(pk=registro.pk).exists())

    def test_el_comando_dice_que_retencion_esta_usando(self):
        """El cron deja su log: ahí se ve si la configuración llegó o no."""
        _configurar_retencion(dias=90, media_dias=15)

        salida = _limpiar()

        self.assertIn("90", salida)
        self.assertIn("15", salida)

    def test_la_retencion_de_media_tambien_sale_de_la_configuracion(self):
        """Mide el efecto en el disco, no el valor de una variable.

        Con los 30 días por defecto el archivo de 10 días sobreviviría; con los
        7 que dice la configuración, no.
        """
        _configurar_retencion(media_dias=7)
        with tempfile.TemporaryDirectory() as tmp:
            huerfano = Path(tmp) / "huerfano.jpg"
            huerfano.write_bytes(b"x")
            antiguo = (timezone.now() - timedelta(days=10)).timestamp()
            os.utime(huerfano, (antiguo, antiguo))

            with override_settings(MEDIA_ROOT=tmp):
                _limpiar(sin_media=False)

            self.assertFalse(huerfano.exists())

    def test_si_la_configuracion_no_responde_el_comando_no_revienta(self):
        """Un comando de cron que revienta no deja rastro más que en su log.

        Lo que hace en ese caso lo fija ``SinRetencionNoSeBorraTests``: termina
        limpio y **sin borrar**. Aquí solo se afirma que no revienta.
        """
        with patch.object(
            ConfiguracionSistema, "get_config", side_effect=DatabaseError("sin tabla"),
        ):
            salida = _limpiar()

        self.assertTrue(salida)

    def test_los_defaults_del_modelo_son_los_del_cron_de_siempre(self):
        """Mover el plazo a la base no puede cambiar lo que ya se venía borrando.

        Son los argumentos que el cron pasaba a mano antes de la Tarea 11
        (``--dias 365 --media-dias 30``). Van como literales: si alguien mueve un
        default, esto tiene que fallar y obligar a pensarlo.
        """
        campos = ConfiguracionSistema._meta
        self.assertEqual(campos.get_field("retencion_dias").default, 365)
        self.assertEqual(campos.get_field("retencion_media_dias").default, 30)


class RetencionDeAxesTests(TestCase):
    """Las tablas de axes, que desde la Tarea 9 ya no se purgan solas.

    ``clean_expired_user_attempts()`` borraba por el umbral del *cool-off*, y
    con ``horas_de_bloqueo = 0`` ese umbral es un siglo atrás
    (``administracion.seguridad.BLOQUEO_SIN_CADUCIDAD``): cada intento fallido
    de login se quedaba en la base para siempre.
    """

    def _intento(self, username, dias):
        intento = AccessAttempt.objects.create(
            user_agent="pruebas", ip_address="10.0.0.1", username=username,
            http_accept="*/*", path_info="/accounts/login/",
            get_data="", post_data="", failures_since_start=1,
        )
        AccessAttempt.objects.filter(pk=intento.pk).update(
            attempt_time=timezone.now() - timedelta(days=dias),
        )
        return intento

    def _fallo(self, username, dias):
        fallo = AccessFailureLog.objects.create(
            user_agent="pruebas", ip_address="10.0.0.1", username=username,
            http_accept="*/*", path_info="/accounts/login/",
        )
        AccessFailureLog.objects.filter(pk=fallo.pk).update(
            attempt_time=timezone.now() - timedelta(days=dias),
        )
        return fallo

    def _acceso(self, username, dias):
        acceso = AccessLog.objects.create(
            user_agent="pruebas", ip_address="10.0.0.1", username=username,
            http_accept="*/*", path_info="/accounts/login/",
        )
        AccessLog.objects.filter(pk=acceso.pk).update(
            attempt_time=timezone.now() - timedelta(days=dias),
        )
        return acceso

    def test_borra_los_intentos_de_axes_antiguos_y_respeta_los_recientes(self):
        viejo = self._intento("viejo", 400)
        nuevo = self._intento("nuevo", 10)

        _limpiar(dias=365)

        self.assertFalse(AccessAttempt.objects.filter(pk=viejo.pk).exists())
        self.assertTrue(AccessAttempt.objects.filter(pk=nuevo.pk).exists())

    def test_borra_los_fallos_de_acceso_antiguos(self):
        viejo = self._fallo("viejo", 400)
        nuevo = self._fallo("nuevo", 10)

        _limpiar(dias=365)

        self.assertFalse(AccessFailureLog.objects.filter(pk=viejo.pk).exists())
        self.assertTrue(AccessFailureLog.objects.filter(pk=nuevo.pk).exists())

    def test_borra_los_accesos_registrados_antiguos(self):
        """``AccessLog`` crece una fila por login correcto y nadie la purga."""
        viejo = self._acceso("viejo", 400)
        nuevo = self._acceso("nuevo", 10)

        _limpiar(dias=365)

        self.assertFalse(AccessLog.objects.filter(pk=viejo.pk).exists())
        self.assertTrue(AccessLog.objects.filter(pk=nuevo.pk).exists())

    def test_la_expiracion_de_axes_se_va_con_su_intento_en_cascada(self):
        """Por eso ``AccessAttemptExpiration`` NO entra en la lista.

        No tiene fecha de intento (su campo es ``expires_at``, que mira al
        futuro) y cuelga de ``AccessAttempt`` con ``on_delete=CASCADE``:
        filtrarla por su cuenta dejaría intentos vivos sin expiración.
        """
        viejo = self._intento("viejo", 400)
        AccessAttemptExpiration.objects.create(
            access_attempt=viejo, expires_at=timezone.now() + timedelta(days=1),
        )

        _limpiar(dias=365)

        self.assertFalse(AccessAttempt.objects.filter(pk=viejo.pk).exists())
        self.assertEqual(AccessAttemptExpiration.objects.count(), 0)

    def test_la_simulacion_no_borra_los_intentos_de_axes(self):
        viejo = self._intento("viejo", 400)

        _limpiar(dias=365, dry_run=True)

        self.assertTrue(AccessAttempt.objects.filter(pk=viejo.pk).exists())


class CronDeLimpiezaTests(SimpleTestCase):
    """El archivo del cron: lo único que hace que la pantalla sirva de algo.

    Si esta prueba se pone roja porque alguien volvió a escribir ``--dias`` en
    el ``.sh``, la pantalla de retención deja de tener efecto en producción
    aunque todo el resto de la suite siga verde.

    Corre en el clon del repositorio (local y CI) y se omite dentro del
    contenedor, que no lleva ``deploy/``; ver ``linea_programada``.
    """

    @property
    def linea_programada(self):
        # `deploy/` queda FUERA de la imagen: el contexto de construcción es
        # `./backend` (docker-compose.yml:25), así que dentro del contenedor de
        # producción —donde AGENTS.md documenta correr la suite— esta carpeta no
        # existe. Si falta la carpeta entera, no estamos en un clon del
        # repositorio y la prueba no aplica; si la carpeta está pero el guion no,
        # eso sí es un fallo real.
        deploy = Path(settings.BASE_DIR).parent / "deploy"
        if not deploy.is_dir():
            self.skipTest(f"sin clon del repositorio: no existe {deploy}")
        guion = deploy / "instalar_cron_limpieza.sh"
        self.assertTrue(guion.is_file(), guion)
        lineas = [
            linea for linea in guion.read_text(encoding="utf-8").splitlines()
            if "limpiar_historial" in linea and linea.lstrip().startswith("0 ")
        ]
        self.assertEqual(len(lineas), 1, lineas)
        return lineas[0]

    def test_el_cron_invoca_el_comando(self):
        self.assertIn("manage.py limpiar_historial", self.linea_programada)

    def test_el_cron_no_pasa_dias_ni_media_dias(self):
        linea = self.linea_programada
        self.assertNotIn("--dias", linea)
        self.assertNotIn("--media-dias", linea)


class SimulacionDeLimpiezaTests(TestCase):
    """El botón «Simular limpieza» de la pantalla."""

    def setUp(self):
        self.config = _configurar_retencion(dias=90)
        self.client.force_login(_cuenta("superadmin", "datos_sa"))

    def _simular(self, **extra):
        return self.client.post(reverse("administracion:simular_limpieza"), extra)

    def test_la_simulacion_no_borra_nada(self):
        viejo = _auditoria_de(400)
        antes = RegistroAuditoria.objects.count()

        self._simular()

        self.assertTrue(RegistroAuditoria.objects.filter(pk=viejo.pk).exists())
        # El único registro nuevo es el renglón de auditoría de la simulación.
        self.assertEqual(RegistroAuditoria.objects.count(), antes + 1)

    def test_la_simulacion_informa_que_borraria(self):
        _auditoria_de(400)
        _auditoria_de(400)

        resp = self._simular()

        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "administracion/datos_form.html")
        self.assertIn("simulacion", resp.context)
        salida = resp.context["simulacion"]
        self.assertIn("Auditoría del sistema: 2", salida)
        self.assertIn("Sesiones vencidas", salida)
        self.assertContains(resp, "Auditoría del sistema: 2")

    def test_la_simulacion_no_recorre_el_disco_de_media(self):
        """El ``os.walk`` de la media no entra en una petición HTTP.

        ``_limpiar_media_huerfana()`` hace un ``os.walk`` sobre ``MEDIA_ROOT``
        y un ``getmtime`` por archivo también en ``--dry-run``: en producción
        eso es el disco entero de media dentro de una petición web, sin cota ni
        tiempo máximo. Es el mismo defecto que obligó a ponerle ``timeout`` al
        SMTP en la Tarea 10.
        """
        with patch("core.management.commands.limpiar_historial.os.walk") as walk:
            self._simular()

        walk.assert_not_called()

    def test_la_simulacion_usa_la_retencion_configurada(self):
        resp = self._simular()
        self.assertIn("90", resp.context["simulacion"])

    def test_la_simulacion_queda_auditada(self):
        self._simular()

        registro = RegistroAuditoria.objects.get(accion="configurar")
        self.assertIn("imulaci", registro.detalle)
        self.assertIn("90", registro.detalle)

    def test_la_simulacion_no_acepta_get(self):
        resp = self.client.get(reverse("administracion:simular_limpieza"))
        self.assertEqual(resp.status_code, 405)

    def test_un_tecnico_no_puede_simular_la_limpieza(self):
        self.client.force_login(_cuenta("tecnico", "datos_tec"))
        _auditoria_de(400)
        antes = RegistroAuditoria.objects.count()

        resp = self._simular()

        self.assertRedirects(resp, reverse("core:dashboard"))
        self.assertEqual(RegistroAuditoria.objects.count(), antes)


class RetencionFormularioTests(TestCase):
    """La pantalla que guarda los dos valores."""

    def setUp(self):
        self.config = ConfiguracionSistema.get_config()
        self.client.force_login(_cuenta("superadmin", "datos_form_sa"))

    def _post(self, **cambios):
        datos = {"retencion_dias": 365, "retencion_media_dias": 30}
        datos.update(cambios)
        return self.client.post(reverse("administracion:datos"), datos)

    def test_la_pantalla_abre_y_renderiza_su_plantilla(self):
        resp = self.client.get(reverse("administracion:datos"))

        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "administracion/datos_form.html")
        self.assertContains(resp, 'name="retencion_dias"')
        self.assertContains(resp, 'name="retencion_media_dias"')

    def test_guardar_cambia_la_retencion_y_queda_auditado(self):
        resp = self._post(retencion_dias=90, retencion_media_dias=15)

        self.assertRedirects(resp, reverse("administracion:datos"))
        config = ConfiguracionSistema.get_config()
        self.assertEqual(config.retencion_dias, 90)
        self.assertEqual(config.retencion_media_dias, 15)
        detalles = " ".join(RegistroAuditoria.objects.values_list("detalle", flat=True))
        self.assertIn("365", detalles)
        self.assertIn("90", detalles)

    def test_el_formulario_rechaza_una_retencion_por_debajo_del_minimo(self):
        resp = self._post(retencion_dias=29)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ConfiguracionSistema.get_config().retencion_dias, 365)
        self.assertTrue(resp.context["form"].errors["retencion_dias"])

    def test_el_formulario_rechaza_una_retencion_de_media_por_debajo_del_minimo(self):
        resp = self._post(retencion_media_dias=6)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ConfiguracionSistema.get_config().retencion_media_dias, 30)
        self.assertTrue(resp.context["form"].errors["retencion_media_dias"])

    def test_el_formulario_rechaza_una_retencion_por_encima_del_tope(self):
        """Capa 1: el máximo también es política, no solo el mínimo."""
        for campo, valor in (
            ("retencion_dias", RETENCION_DIAS_MAXIMO + 1),
            ("retencion_media_dias", RETENCION_MEDIA_DIAS_MAXIMO + 1),
        ):
            with self.subTest(campo=campo):
                antes = getattr(ConfiguracionSistema.get_config(), campo)
                resp = self._post(**{campo: valor})
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.context["form"].errors[campo])
                self.assertEqual(
                    getattr(ConfiguracionSistema.get_config(), campo), antes
                )

    def test_el_formulario_acepta_los_valores_justo_en_el_tope(self):
        """Contraprueba: el tope es el último valor válido, no el primero inválido."""
        resp = self._post(
            retencion_dias=RETENCION_DIAS_MAXIMO,
            retencion_media_dias=RETENCION_MEDIA_DIAS_MAXIMO,
        )
        self.assertRedirects(resp, reverse("administracion:datos"))
        config = ConfiguracionSistema.get_config()
        self.assertEqual(config.retencion_dias, RETENCION_DIAS_MAXIMO)
        self.assertEqual(config.retencion_media_dias, RETENCION_MEDIA_DIAS_MAXIMO)

    def test_el_minimo_tambien_vale_fuera_del_formulario(self):
        """La regla vive en el modelo: un comando o una importación la cumplen."""
        from django.core.exceptions import ValidationError

        config = ConfiguracionSistema.get_config()
        config.retencion_dias = 29
        with self.assertRaises(ValidationError):
            config.full_clean()

    def test_un_tecnico_no_puede_abrir_la_pantalla(self):
        self.client.force_login(_cuenta("tecnico", "datos_tec_ver"))
        resp = self.client.get(reverse("administracion:datos"))
        self.assertRedirects(resp, reverse("core:dashboard"))


class TopesDeLaRetencionTests(TestCase):
    """El mismo defecto del C1, en la ruta de retención.

    ``handle()`` hace ``timezone.now() - timedelta(days=dias)`` con el valor que
    salga de la configuración, y los dos campos de la Tarea 11 nacieron solo con
    mínimo. Con un valor grande eso es ``OverflowError``: el cron semanal muere
    y **nada se purga nunca**, con el fallo escondido en
    ``/var/log/sysadmin-limpiar-historial.log``.

    Como en el C1, el tope del campo no basta: ``queryset.update()`` se salta
    los validadores, así que el comando los reaplica al resolver. Todas las
    escrituras de aquí van por ``update()`` a propósito.
    """

    def test_los_topes_del_comando_coinciden_con_los_del_modelo(self):
        from django.core.validators import MaxValueValidator

        esperado = {
            "retencion_dias": RETENCION_DIAS_MAXIMO,
            "retencion_media_dias": RETENCION_MEDIA_DIAS_MAXIMO,
        }
        for campo, tope in esperado.items():
            with self.subTest(campo=campo):
                maximos = [
                    v.limit_value
                    for v in ConfiguracionSistema._meta.get_field(campo).validators
                    if isinstance(v, MaxValueValidator)
                ]
                self.assertEqual(maximos, [tope])

    def test_una_retencion_desbordante_no_revienta_el_comando(self):
        """La prueba del defecto: hoy el comando lanza OverflowError."""
        _configurar_retencion(dias=VALOR_ABSURDO)

        salida = _limpiar(dry_run=True)

        self.assertIn(f"Retención en uso: {RETENCION_DIAS_MAXIMO} días", salida)
        self.assertIn("Total registros afectados", salida)

    def test_una_retencion_de_media_desbordante_no_revienta_el_comando(self):
        _configurar_retencion(media_dias=VALOR_ABSURDO)

        salida = _limpiar(dry_run=True)

        self.assertIn(
            f"{RETENCION_MEDIA_DIAS_MAXIMO} días de archivos de media", salida,
        )

    def test_un_valor_por_debajo_del_minimo_tambien_se_acota(self):
        """Un 0 llega por la misma puerta que el máximo: por un UPDATE."""
        _configurar_retencion(dias=0, media_dias=0)

        salida = _limpiar(dry_run=True)

        self.assertIn(
            f"Retención en uso: {RETENCION_DIAS_MINIMO} días de historial · "
            f"{RETENCION_MEDIA_DIAS_MINIMO} días de archivos de media",
            salida,
        )

    def test_un_argumento_explicito_absurdo_tambien_se_acota(self):
        """La bandera de la línea de comandos gana, pero no por encima del tope.

        Es la puerta de un humano depurando con la unidad equivocada, y acaba en
        el mismo ``timedelta`` que la columna.
        """
        salida = _limpiar(dry_run=True, dias=VALOR_ABSURDO)

        self.assertIn(f"Retención en uso: {RETENCION_DIAS_MAXIMO} días", salida)

    def test_los_valores_de_siempre_pasan_intactos(self):
        """Contraprueba: acotar no puede cambiar lo que una instalación ya borra."""
        _configurar_retencion(dias=365, media_dias=30)
        viejo = _auditoria_de(400)
        reciente = _auditoria_de(10)

        salida = _limpiar()

        self.assertIn(
            "Retención en uso: 365 días de historial · 30 días de archivos de media",
            salida,
        )
        self.assertFalse(RegistroAuditoria.objects.filter(pk=viejo.pk).exists())
        self.assertTrue(RegistroAuditoria.objects.filter(pk=reciente.pk).exists())

    def test_la_simulacion_de_la_pantalla_sobrevive_a_una_retencion_desbordante(self):
        """La pantalla de Datos no da 500 —ya atrapaba la excepción—, pero sin
        acotar devolvía una simulación vacía y un aviso de fallo, o sea nada."""
        _configurar_retencion(dias=VALOR_ABSURDO)
        self.client.force_login(_cuenta("superadmin", "datos_tope_sa"))

        resp = self.client.post(reverse("administracion:simular_limpieza"))

        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            f"Retención en uso: {RETENCION_DIAS_MAXIMO} días",
            resp.context["simulacion"],
        )
        self.assertNotContains(resp, "No se pudo simular")

    def test_la_migracion_acota_la_retencion_ya_guardada(self):
        """Un ``AlterField`` no revisa los datos, y con el ``full_clean()`` del
        ``save()`` una fila heredada fuera de rango deja de ser guardable."""
        from importlib import import_module

        from django.apps import apps as registro_de_apps

        migracion = import_module(
            "administracion.migrations.0014_topes_retencion"
        )
        _configurar_retencion(dias=VALOR_ABSURDO, media_dias=VALOR_ABSURDO)

        migracion.acotar_la_retencion(registro_de_apps, None)

        config = ConfiguracionSistema.objects.get(pk=1)
        self.assertEqual(config.retencion_dias, RETENCION_DIAS_MAXIMO)
        self.assertEqual(config.retencion_media_dias, RETENCION_MEDIA_DIAS_MAXIMO)
        # Y la fila vuelve a ser guardable, que es para lo que está la migración.
        config.nombre_empresa = "Clinica X"
        config.save()

    def test_la_migracion_no_toca_una_fila_sana(self):
        from importlib import import_module

        from django.apps import apps as registro_de_apps

        migracion = import_module(
            "administracion.migrations.0014_topes_retencion"
        )
        _configurar_retencion(dias=365, media_dias=30)

        migracion.acotar_la_retencion(registro_de_apps, None)

        config = ConfiguracionSistema.objects.get(pk=1)
        self.assertEqual(config.retencion_dias, 365)
        self.assertEqual(config.retencion_media_dias, 30)


class SinRetencionNoSeBorraTests(TestCase):
    """Si no se puede leer la retención, la limpieza NO borra.

    La asimetría es el argumento: un respaldo que borra de menos es inofensivo
    —los datos se acumulan una semana y el cron vuelve el domingo—, mientras uno
    que borra de más es **irreversible** y destruye justo lo que el
    administrador eligió conservar. Ante una operación destructiva y con duda,
    no se borra.

    Y va contra el instinto del resto del módulo a propósito: aquí se **falla
    cerrado**, mientras ``modulos_activos()`` y el resolvedor de permisos fallan
    abiertos para no esconder la aplicación. En una limpieza, «fallar abierto»
    significa destruir.
    """

    def _sin_configuracion(self):
        return patch.object(
            ConfiguracionSistema, "get_config", side_effect=DatabaseError("sin tabla"),
        )

    def test_las_filas_viejas_siguen_ahi(self):
        """La prueba que mide el efecto, y es la del ruling."""
        registro = _auditoria_de(400)

        with self._sin_configuracion():
            _limpiar()

        self.assertTrue(RegistroAuditoria.objects.filter(pk=registro.pk).exists())

    def test_el_aviso_dice_que_no_se_borro_nada(self):
        """Un operador que lea el log del cron no puede confundir «no corrió»
        con «no había nada que borrar»."""
        _auditoria_de(400)

        with self._sin_configuracion():
            salida = _limpiar()

        self.assertIn(AVISO_SIN_RETENCION, salida)
        self.assertIn("NO SE BORRÓ NADA", salida)
        # Y no puede quedar el renglón que hace creer que la limpieza corrió.
        self.assertNotIn("Total registros afectados", salida)
        self.assertNotIn("Retención en uso", salida)

    def test_la_simulacion_tampoco_inventa_un_conteo(self):
        """``--dry-run`` existe para decir qué haría la corrida de verdad.

        Con la retención ilegible, la corrida de verdad no borraría nada, así
        que un conteo calculado con un respaldo sería un informe **falso** —y es
        el que la pantalla de Datos le muestra al administrador—.
        """
        _auditoria_de(400)

        with self._sin_configuracion():
            salida = _limpiar(dry_run=True)

        self.assertIn(AVISO_SIN_RETENCION, salida)
        self.assertNotIn("Auditoría del sistema:", salida)

    def test_con_una_sola_bandera_explicita_tampoco_se_borra(self):
        """El otro plazo venía de la configuración, así que sigue sin saberse."""
        registro = _auditoria_de(400)

        with self._sin_configuracion():
            salida = _limpiar(dias=365)

        self.assertTrue(RegistroAuditoria.objects.filter(pk=registro.pk).exists())
        self.assertIn(AVISO_SIN_RETENCION, salida)

    def test_con_las_dos_banderas_explicitas_borra_igual(self):
        """Contraprueba: con los dos plazos dados, la base no hace falta.

        Es la vía del humano depurando y la que impide que el ruling se
        convierta en «el comando ya no borra nunca».
        """
        registro = _auditoria_de(400)
        reciente = _auditoria_de(10)

        with self._sin_configuracion():
            salida = _limpiar(dias=365, media_dias=30)

        self.assertFalse(RegistroAuditoria.objects.filter(pk=registro.pk).exists())
        self.assertTrue(RegistroAuditoria.objects.filter(pk=reciente.pk).exists())
        self.assertNotIn(AVISO_SIN_RETENCION, salida)
        self.assertIn("Retención en uso: 365 días de historial", salida)

    def test_con_la_configuracion_legible_sigue_borrando_como_hoy(self):
        """La otra contraprueba: el camino normal no se toca."""
        _configurar_retencion(dias=90, media_dias=15)
        registro = _auditoria_de(400)
        reciente = _auditoria_de(10)

        salida = _limpiar()

        self.assertFalse(RegistroAuditoria.objects.filter(pk=registro.pk).exists())
        self.assertTrue(RegistroAuditoria.objects.filter(pk=reciente.pk).exists())
        self.assertNotIn(AVISO_SIN_RETENCION, salida)
        self.assertIn("Retención en uso: 90 días de historial · 15 días", salida)

    # NO hay prueba de la pantalla de Datos para este caso, y es a propósito:
    # `simular_limpieza` llama a `ConfiguracionSistema.get_config()` por su
    # cuenta antes del comando (necesita `config` para el formulario), así que
    # con la base sin responder la pantalla entera no se puede pintar — igual
    # que cualquier otra pantalla de configuración. Lo que sí se verifica es que
    # el aviso va a `stdout`/`stderr`, que es lo que la vista recoge en
    # `simulacion` y pinta: lo prueba `test_el_aviso_dice_que_no_se_borro_nada`.


class MensajesDeErrorTests(TestCase):
    """Añadido declarado: los mensajes de error salían sin color en toda la app.

    ``base.html`` pinta ``alert alert-{{ message.tags }}`` y la etiqueta que
    Django da a ``messages.ERROR`` es ``error``, así que el HTML real decía
    ``alert-error``, una clase que **no existe** en Bootstrap 5 (es
    ``alert-danger``). Resultado: todos los avisos de error de todas las
    pantallas salían con la caja pero en gris. El arreglo es ``MESSAGE_TAGS``
    en los settings, así que vale para todas las páginas de una vez.
    """

    def setUp(self):
        ConfiguracionSistema.get_config()
        self.client.force_login(_cuenta("superadmin", "mensajes_sa"))

    def test_message_tags_mapea_error_a_danger(self):
        from django.contrib.messages import constants

        self.assertEqual(settings.MESSAGE_TAGS[constants.ERROR], "danger")

    def test_un_mensaje_de_error_se_pinta_con_alert_danger(self):
        resp = self.client.post(
            reverse("administracion:datos"),
            {"retencion_dias": 29, "retencion_media_dias": 30},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alert-danger")
        self.assertNotContains(resp, "alert-error")

    def test_los_demas_niveles_no_se_tocan(self):
        """``success``, ``warning`` e ``info`` ya coinciden con Bootstrap."""
        resp = self.client.post(
            reverse("administracion:datos"),
            {"retencion_dias": 90, "retencion_media_dias": 30},
            follow=True,
        )

        self.assertContains(resp, "alert-success")
