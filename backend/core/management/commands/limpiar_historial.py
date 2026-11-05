"""Limpieza del historial: la tarea semanal que recorta lo que ya no se mira.

Cinco cosas de este comando no son de estilo y conviene no deshacerlas:

1. **Los dos plazos salen de ``ConfiguracionSistema``**, no de un valor fijo.
   Los argumentos ``--dias`` y ``--media-dias`` nacen en ``None`` y solo se
   resuelven desde la base cuando llegan así, de modo que un humano depurando
   puede seguir forzando un valor en la línea de comandos. Por eso mismo el
   cron de ``deploy/instalar_cron_limpieza.sh`` **no** los pasa: si los pasara,
   la pantalla de retención quedaría de decorado y el programado —el único que
   corre de verdad— seguiría usando los 365 días de siempre.

2. **Si la retención no se puede leer, NO se borra.** El comando tolera que la
   base no responda —uno de cron que revienta no deja rastro más que en su log—
   pero termina sin tocar nada y lo dice (``AVISO_SIN_RETENCION``, por
   ``stderr`` para que se vea en ese log).

   La asimetría es el argumento: un respaldo que borra **de menos** es
   inofensivo, porque los datos se acumulan una semana y el cron vuelve el
   domingo siguiente; uno que borra **de más** es irreversible y destruye justo
   lo que el administrador eligió conservar. Ante una operación destructiva y
   con duda, no se borra.

   **Esto va contra el instinto del resto del módulo y es deliberado.** En esta
   rama el criterio general es *fallar abierto* cuando la configuración no se
   puede leer: ``administracion.registro.modulos_activos()`` da todos los
   módulos por activos para que la aplicación no se esconda, y el resolvedor de
   permisos cae a la matriz del código. Aquí el mismo instinto se invierte,
   porque en una limpieza «fallar abierto» significa **destruir**. Quien venga
   detrás verá el patrón del resto del módulo: esto no es una excepción por
   descuido.

   Por el mismo motivo **los dos plazos se acotan al resolverlos**
   (``_plazos()``): el comando no se fía de la columna, porque un
   ``queryset.update()`` se salta los validadores del modelo.

3. **``--sin-media`` existe para la pantalla**, no para el cron.
   ``_limpiar_media_huerfana()`` hace un ``os.walk`` sobre ``MEDIA_ROOT`` y un
   ``getmtime`` por archivo también en ``--dry-run``, sin cota: dentro de una
   petición HTTP eso es el disco de media entero. La simulación de la pantalla
   se queda en las tablas; el cron sí barre el disco.

4. **La cola de correo se purga por los dos lados.** No solo los enviados:
   también los que nunca salieron, que eran inmortales porque una fila con
   error es ``enviado=False`` por definición. En esa columna va la respuesta
   del servidor, que puede repetir la credencial que le mandamos.

5. **Los modelos con archivos se descubren con ``apps.get_models()``**, nunca
   con una lista escrita a mano (``_modelos_con_archivos()``), y si la lectura
   de referencias falla, el barrido de ``media`` también falla cerrado sin
   borrar nada. Una lista a mano dejó fuera 5 de los 8 campos ``FileField`` del
   proyecto y borró 179 archivos referenciados el 2026-11-01.
"""

import os
from datetime import timedelta

from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.core.management.base import BaseCommand
from django.db import DatabaseError, Error
from django.utils import timezone

from core.utils import acotado

# NO hay respaldo para cuando `ConfiguracionSistema` no se puede leer: si la
# política no se conoce, no se borra. Ver la regla 2 del docstring de arriba y
# `AVISO_SIN_RETENCION`. Hasta esta versión había uno de 365/30 (los números que
# el cron pasaba a mano) y borraba con él, que es el fallo que esto cierra.
AVISO_SIN_RETENCION = (
    "NO SE BORRÓ NADA: no se pudo leer la retención de la configuración, y una "
    "limpieza sin su política borraría más de lo que el administrador eligió "
    "conservar. Lo que se borra no se puede recuperar, así que ante la duda no "
    "se borra. Revisa la base de datos y vuelve a correr la limpieza, o pasa "
    "--dias y --media-dias explícitos si hace falta correrla ya."
)


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
        plazos = self._plazos(options)
        if plazos is None:
            # Regla 2 del docstring: si la política no se conoce, no se borra.
            # Se sale ANTES de contar cualquier cosa, para que ni el log del
            # cron ni la simulación de la pantalla muestren un informe de una
            # limpieza que no ocurrió.
            #
            # El aviso va por `stderr` y no por un logger porque el cron recoge
            # las dos salidas en el mismo archivo y un `logger.warning` lo
            # dejaría dos veces, como si hubiera fallado dos veces. Por
            # `stderr` lo ve ese log y también la simulación de la pantalla.
            self.stderr.write(AVISO_SIN_RETENCION)
            return
        dias, media_dias = plazos
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
            if huerfanos is not None:
                self.stdout.write(f"Archivos huérfanos de media: {huerfanos}")

        modo = "(simulación)" if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"Total registros afectados: {total_borrados} {modo}"))

    def _plazos(self, options):
        """Devuelve ``(dias, media_dias)``: el argumento explícito, o la configuración.

        El argumento de la línea de comandos gana siempre, para que un humano
        depurando pueda forzar un valor. Solo se consulta la base cuando falta
        alguno de los dos, así que una invocación con las dos banderas no
        escribe nada (``get_config()`` es un ``get_or_create``).

        **Los dos valores se acotan al final, venga de donde venga el número.**
        No es una comodidad: ``handle()`` construye con ellos un
        ``timezone.now() - timedelta(days=...)``, y ahí un valor grande lanza
        ``OverflowError`` —el cron muere y no purga nada, con el fallo escondido
        en su log— mientras un 0 pone el corte en «ahora» y **borra el historial
        entero sin avisar**. Los validadores del campo no alcanzan: un
        ``queryset.update()`` se los salta, igual que la bandera de la línea de
        comandos, que no pasa por el modelo en absoluto.
        """
        # El import va aquí dentro por el mismo motivo que en
        # `_retencion_configurada()`: no cargar `administracion` al importar el
        # módulo del comando.
        from administracion.models import (
            RETENCION_DIAS_MAXIMO,
            RETENCION_DIAS_MINIMO,
            RETENCION_MEDIA_DIAS_MAXIMO,
            RETENCION_MEDIA_DIAS_MINIMO,
        )

        dias = options["dias"]
        media_dias = options["media_dias"]
        if dias is None or media_dias is None:
            configurada = self._retencion_configurada()
            if configurada is None:
                # Falta al menos un plazo y la configuración no se puede leer:
                # no hay política que aplicar. Avisa `handle()`, que es quien
                # sabe que esto aborta la limpieza entera.
                return None
            dias_config, media_config = configurada
            if dias is None:
                dias = dias_config
            if media_dias is None:
                media_dias = media_config
        # El aviso de los topes va por `stderr` y no por un logger, por lo mismo
        # que el de `AVISO_SIN_RETENCION`: el cron recoge las dos salidas en el
        # mismo archivo y un logger dejaría el aviso dos veces.
        return (
            acotado(
                dias, RETENCION_DIAS_MINIMO, RETENCION_DIAS_MAXIMO,
                "los días de historial", self.stderr.write,
            ),
            acotado(
                media_dias, RETENCION_MEDIA_DIAS_MINIMO, RETENCION_MEDIA_DIAS_MAXIMO,
                "los días de archivos de media", self.stderr.write,
            ),
        )

    def _retencion_configurada(self):
        """Los dos plazos de ``ConfiguracionSistema``, o ``None`` si no se leen.

        El import va aquí dentro para no cargar `administracion` al importar el
        módulo del comando. El ``except`` cubre la base a medio migrar o la
        tabla de configuración ausente: el comando no revienta, pero **tampoco
        inventa un plazo**. Hasta esta versión devolvía unos respaldos de 365 y
        30 días y borraba con ellos, que es el fallo que esto cierra: ante una
        instalación con retención mayor, esos respaldos borraban de más y lo
        borrado no se recupera. Quien decide qué hacer con el ``None`` es
        ``handle()``.
        """
        from administracion.models import ConfiguracionSistema

        try:
            config = ConfiguracionSistema.get_config()
        except DatabaseError:
            return None
        return config.retencion_dias, config.retencion_media_dias

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

    def _modelos_con_archivos(self):
        """Todos los modelos registrados que tienen algún ``FileField``.

        Se descubren con ``apps.get_models()`` en vez de mantener una lista a
        mano: hasta el incidente del 2026-11-01 la lista fija solo incluía
        ``[Activo, Movimiento, ActaAsignacion]`` (3 de los 8 campos de archivo
        del proyecto) y la limpieza semanal borró los archivos de Documentos,
        Mantenimiento y Usuarios cuando cumplieron 30 días. ``ImageField``
        hereda de ``FileField``, así que ``isinstance(f, FileField)`` cubre los
        dos.
        """
        from django.apps import apps
        from django.db.models import FileField

        return [
            modelo
            for modelo in apps.get_models()
            if any(isinstance(f, FileField) for f in modelo._meta.fields)
        ]

    def _archivos_referenciados(self):
        """Rutas relativas a ``MEDIA_ROOT`` que algún registro tiene guardadas."""
        from django.db.models import FileField

        referenciados = set()
        for modelo in self._modelos_con_archivos():
            for field in modelo._meta.fields:
                if isinstance(field, FileField):
                    valores = modelo.objects.exclude(**{field.name: ""}).values_list(
                        field.name, flat=True
                    )
                    for valor in valores:
                        if valor:
                            referenciados.add(valor.replace("\\", "/"))
        return referenciados

    def _limpiar_media_huerfana(self, corte, dry_run):
        """Elimina archivos en MEDIA_ROOT no referenciados por ningún modelo.

        Recorre el disco entero y hace un ``getmtime`` por archivo **también en
        ``--dry-run``**: lo único que se salta es el ``os.remove``. Por eso la
        pantalla llama al comando con ``--sin-media`` y esto solo corre desde el
        cron, donde no hay nadie esperando una respuesta HTTP.

        Si la consulta de referencias falla, **no borra nada**: los archivos de
        los modelos que no se alcanzaron a consultar parecerían huérfanos y se
        perderían sin vuelta atrás.
        """
        try:
            referenciados = self._archivos_referenciados()
        except Error:
            self.stderr.write(
                "Archivos huérfanos de media: no se revisó el disco porque no "
                "se pudieron leer las referencias de la base de datos."
            )
            return None

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
