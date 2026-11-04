"""Limpieza del historial: la tarea semanal que recorta lo que ya no se mira.

Cuatro cosas de este comando no son de estilo y conviene no deshacerlas:

1. **Los dos plazos salen de ``ConfiguracionSistema``**, no de un valor fijo.
   Los argumentos ``--dias`` y ``--media-dias`` nacen en ``None`` y solo se
   resuelven desde la base cuando llegan así, de modo que un humano depurando
   puede seguir forzando un valor en la línea de comandos. Por eso mismo el
   cron de ``deploy/instalar_cron_limpieza.sh`` **no** los pasa: si los pasara,
   la pantalla de retención quedaría de decorado y el programado —el único que
   corre de verdad— seguiría usando los 365 días de siempre.

2. **La lectura de la configuración tolera que la base no responda** y cae a
   los respaldos de abajo, que son los números que el cron pasaba a mano antes
   de este cambio. Un comando de cron que revienta no deja rastro más que en su
   log. El aviso va a ``stderr`` para que se vea en ese log.

3. **``--sin-media`` existe para la pantalla**, no para el cron.
   ``_limpiar_media_huerfana()`` hace un ``os.walk`` sobre ``MEDIA_ROOT`` y un
   ``getmtime`` por archivo también en ``--dry-run``, sin cota: dentro de una
   petición HTTP eso es el disco de media entero. La simulación de la pantalla
   se queda en las tablas; el cron sí barre el disco.

4. **La cola de correo se purga por los dos lados.** No solo los enviados:
   también los que nunca salieron, que eran inmortales porque una fila con
   error es ``enviado=False`` por definición. En esa columna va la respuesta
   del servidor, que puede repetir la credencial que le mandamos.
"""

import os
from datetime import timedelta

from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.core.management.base import BaseCommand
from django.db import DatabaseError
from django.utils import timezone

# Respaldos para cuando `ConfiguracionSistema` no se puede leer. Son los mismos
# números que los `default` de los campos del modelo y hay una prueba que lo
# exige (`test_los_respaldos_coinciden_con_los_defaults_del_modelo`): si se
# separan, una base que no responde cambiaría la política de retención.
RETENCION_DIAS_POR_DEFECTO = 365
RETENCION_MEDIA_DIAS_POR_DEFECTO = 30


class Command(BaseCommand):
    help = (
        "Limpia logs, auditoría, intentos de acceso, sesiones vencidas y "
        "archivos de media antiguos. Sin argumentos usa los plazos de la "
        "pantalla Configuración › Datos."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias",
            type=int,
            default=None,
            help=(
                "Conservar registros de los últimos N días. Sin este argumento "
                "se usa «Días de historial que se conservan» de la configuración."
            ),
        )
        parser.add_argument(
            "--media-dias",
            type=int,
            default=None,
            help=(
                "Borrar archivos de media no referenciados modificados hace más "
                "de N días. Sin este argumento se usa el valor de la configuración."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que borraría sin eliminar nada.",
        )
        parser.add_argument(
            "--sin-media",
            action="store_true",
            help=(
                "No revisar el disco de media. Lo usa la simulación de la "
                "pantalla, que corre dentro de una petición web."
            ),
        )

    def handle(self, *args, **options):
        # Los plazos se resuelven ANTES de construir los cortes: con
        # `default=None` un `timedelta(days=None)` sería un TypeError.
        dias, media_dias = self._plazos(options)
        dry_run = options["dry_run"]
        sin_media = options["sin_media"]

        corte = timezone.now() - timedelta(days=dias)
        corte_media = timezone.now() - timedelta(days=media_dias)

        self.stdout.write(
            f"Retención en uso: {dias} días de historial · "
            f"{media_dias} días de archivos de media"
        )

        modelos = self._modelos_a_limpiar()
        total_borrados = 0

        for nombre, campo_fecha, qs in modelos:
            qs_viejos = qs.filter(**{f"{campo_fecha}__lt": corte})
            cuenta = qs_viejos.count()
            total_borrados += cuenta
            self.stdout.write(f"{nombre}: {cuenta} registros anteriores a {corte.date()}")
            if not dry_run and cuenta:
                qs_viejos.delete()

        # LogEntry de admin usa action_time
        log_borrados = LogEntry.objects.filter(action_time__lt=corte).count()
        total_borrados += log_borrados
        self.stdout.write(f"LogEntry admin: {log_borrados} registros anteriores a {corte.date()}")
        if not dry_run and log_borrados:
            LogEntry.objects.filter(action_time__lt=corte).delete()

        # Notificaciones leídas antiguas
        from notificaciones.models import Notificacion, NotificacionEmail

        notif_borradas = Notificacion.objects.filter(leida=True, fecha_creacion__lt=corte).count()
        total_borrados += notif_borradas
        self.stdout.write(f"Notificaciones leídas: {notif_borradas}")
        if not dry_run and notif_borradas:
            Notificacion.objects.filter(leida=True, fecha_creacion__lt=corte).delete()

        email_borrados = NotificacionEmail.objects.filter(
            enviado=True, fecha_enviado__lt=corte
        ).count()
        total_borrados += email_borrados
        self.stdout.write(f"Emails enviados: {email_borrados}")
        if not dry_run and email_borrados:
            NotificacionEmail.objects.filter(enviado=True, fecha_enviado__lt=corte).delete()

        # Los que NUNCA salieron. Eran inmortales: la purga de arriba solo mira
        # `enviado=True` y una fila con error es `enviado=False` por definición,
        # así que el texto de la respuesta del servidor —que puede repetir la
        # credencial que le mandamos— se quedaba para siempre y entraba en cada
        # respaldo. Se filtra por `fecha_creacion` y no por la fecha del último
        # intento, que no se guarda: pasada la retención general, un correo sin
        # enviar ya no se va a enviar.
        sin_enviar_viejos = NotificacionEmail.objects.filter(
            enviado=False, fecha_creacion__lt=corte
        )
        email_sin_enviar = sin_enviar_viejos.count()
        total_borrados += email_sin_enviar
        self.stdout.write(f"Emails sin enviar antiguos: {email_sin_enviar}")
        if not dry_run and email_sin_enviar:
            sin_enviar_viejos.delete()

        # Sesiones vencidas (lo que hace clearsessions). Incluyen vistas previas de
        # importación de contraseñas abandonadas: claves cifradas con la clave del
        # vault de ese momento, que rotar_clave_vault no re-cifra.
        from django.contrib.sessions.models import Session

        vencidas = Session.objects.filter(expire_date__lt=timezone.now())
        sesiones_borradas = vencidas.count()
        total_borrados += sesiones_borradas
        self.stdout.write(f"Sesiones vencidas: {sesiones_borradas}")
        if not dry_run and sesiones_borradas:
            vencidas.delete()

        # Archivos huérfanos de media
        if sin_media:
            self.stdout.write(
                "Archivos huérfanos de media: no revisado (--sin-media). "
                "El barrido del disco lo hace la tarea programada."
            )
        else:
            huerfanos = self._limpiar_media_huerfana(corte_media, dry_run)
            self.stdout.write(f"Archivos huérfanos de media: {huerfanos}")

        modo = "(simulación)" if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"Total registros afectados: {total_borrados} {modo}"))

    def _plazos(self, options):
        """Devuelve ``(dias, media_dias)``: el argumento explícito, o la configuración.

        El argumento de la línea de comandos gana siempre, para que un humano
        depurando pueda forzar un valor. Solo se consulta la base cuando falta
        alguno de los dos, así que una invocación con las dos banderas no
        escribe nada (``get_config()`` es un ``get_or_create``).
        """
        dias = options["dias"]
        media_dias = options["media_dias"]
        if dias is None or media_dias is None:
            dias_config, media_config = self._retencion_configurada()
            if dias is None:
                dias = dias_config
            if media_dias is None:
                media_dias = media_config
        return dias, media_dias

    def _retencion_configurada(self):
        """Los dos plazos de ``ConfiguracionSistema``, con respaldo si falla.

        El import va aquí dentro para no cargar `administracion` al importar el
        módulo del comando. El ``except`` cubre la base a medio migrar o la
        tabla de configuración ausente: en esos casos el comando sigue con los
        respaldos históricos en vez de abortar la limpieza entera.
        """
        from administracion.models import ConfiguracionSistema

        try:
            config = ConfiguracionSistema.get_config()
            return config.retencion_dias, config.retencion_media_dias
        except DatabaseError:
            # Va a `stderr` y no al logger: el cron redirige las dos salidas al
            # mismo archivo, así que un `logger.warning` además dejaría el aviso
            # dos veces y parecería que falló dos veces. Por stderr lo ve el log
            # del cron y también la simulación de la pantalla.
            self.stderr.write(
                "No se pudo leer la retención de la configuración; se usan los "
                f"respaldos de {RETENCION_DIAS_POR_DEFECTO} y "
                f"{RETENCION_MEDIA_DIAS_POR_DEFECTO} días."
            )
            return RETENCION_DIAS_POR_DEFECTO, RETENCION_MEDIA_DIAS_POR_DEFECTO

    def _modelos_a_limpiar(self):
        """Tablas que se recortan por antigüedad, con su campo de fecha.

        Las tres de axes entran desde la Tarea 11 y es deuda que creó la 9:
        ``clean_expired_user_attempts()`` purgaba los intentos por el umbral del
        *cool-off*, pero con ``horas_de_bloqueo = 0`` ese umbral es un siglo
        atrás (``administracion.seguridad.BLOQUEO_SIN_CADUCIDAD``) y ya no borra
        nada. ``AccessLog`` además nunca se purgó sola: axes solo la toca con
        ``axes_reset_logs``, que aquí no corre nadie, y crece una fila por login
        correcto.

        ``AccessAttemptExpiration`` **no** está a propósito: su única fecha es
        ``expires_at`` (mira al futuro, no es la edad del registro) y cuelga de
        ``AccessAttempt`` con ``on_delete=CASCADE``, así que se va con su
        intento. Filtrarla por su cuenta dejaría intentos vivos sin expiración.
        Además, con ``AXES_USE_ATTEMPT_EXPIRATION`` en su valor por defecto
        (``False``) esta instalación no escribe ninguna fila ahí.
        """
        from axes.models import AccessAttempt, AccessFailureLog, AccessLog

        from administracion.models import RegistroAuditoria
        from passwords.models import AccesoLog
        from yule.models import SincronizacionLog

        return [
            ("Auditoría del sistema", "fecha", RegistroAuditoria.objects),
            ("Accesos a la bóveda de contraseñas", "fecha", AccesoLog.objects),
            ("Sincronizaciones de Yule", "fecha_inicio", SincronizacionLog.objects),
            ("Intentos de acceso fallidos (axes)", "attempt_time", AccessAttempt.objects),
            ("Fallos de acceso registrados (axes)", "attempt_time", AccessFailureLog.objects),
            ("Accesos correctos registrados (axes)", "attempt_time", AccessLog.objects),
        ]

    def _limpiar_media_huerfana(self, corte, dry_run):
        """Elimina archivos en MEDIA_ROOT no referenciados por modelos conocidos.

        Sólo toma campos FileField/ImageField de modelos propios. Ajustar a medida
        que se agreguen nuevos campos de archivo.

        Recorre el disco entero y hace un ``getmtime`` por archivo **también en
        ``--dry-run``**: lo único que se salta es el ``os.remove``. Por eso la
        pantalla llama al comando con ``--sin-media`` y esto solo corre desde el
        cron, donde no hay nadie esperando una respuesta HTTP.
        """
        from django.db.models import FileField

        from inventario.models import ActaAsignacion, Activo, Movimiento

        modelos_con_archivos = [Activo, Movimiento, ActaAsignacion]
        referenciados = set()

        for modelo in modelos_con_archivos:
            for field in modelo._meta.fields:
                if isinstance(field, FileField):
                    for valor in modelo.objects.exclude(**{field.name: ""}).values_list(field.name, flat=True):
                        if valor:
                            referenciados.add(valor)

        media_root = getattr(settings, "MEDIA_ROOT", None)
        if not media_root or not os.path.isdir(media_root):
            return 0

        borrados = 0
        for root, _dirs, files in os.walk(media_root):
            for nombre in files:
                ruta_abs = os.path.join(root, nombre)
                ruta_rel = os.path.relpath(ruta_abs, media_root)
                # Normalizar separadores
                ruta_rel = ruta_rel.replace(os.sep, "/")
                if ruta_rel in referenciados:
                    continue
                if os.path.getmtime(ruta_abs) < corte.timestamp():
                    borrados += 1
                    if not dry_run:
                        try:
                            os.remove(ruta_abs)
                        except OSError:
                            pass
        return borrados
