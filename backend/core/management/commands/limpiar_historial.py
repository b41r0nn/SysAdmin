from datetime import timedelta

from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Limpia logs, auditoría y archivos de media antiguos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias",
            type=int,
            default=365,
            help="Conservar registros de los últimos N días (default: 365).",
        )
        parser.add_argument(
            "--media-dias",
            type=int,
            default=30,
            help="Borrar archivos de media no referenciados modificados hace más de N días (default: 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que borraría sin eliminar nada.",
        )

    def handle(self, *args, **options):
        dias = options["dias"]
        media_dias = options["media_dias"]
        dry_run = options["dry_run"]

        corte = timezone.now() - timedelta(days=dias)
        corte_media = timezone.now() - timedelta(days=media_dias)

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

        # Archivos huérfanos de media
        huérfanos = self._limpiar_media_huerfana(corte_media, dry_run)
        self.stdout.write(f"Archivos huérfanos de media: {huérfanos}")

        modo = "(simulación)" if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"Total registros afectados: {total_borrados} {modo}"))

    def _modelos_a_limpiar(self):
        from administracion.models import RegistroAuditoria
        from passwords.models import AccesoLog
        from yule.models import SincronizacionLog

        return [
            ("RegistroAuditoria", "fecha", RegistroAuditoria.objects),
            ("AccesoLog", "fecha", AccesoLog.objects),
            ("SincronizacionLog", "fecha_inicio", SincronizacionLog.objects),
        ]

    def _limpiar_media_huerfana(self, corte, dry_run):
        """Elimina archivos en MEDIA_ROOT no referenciados por modelos conocidos.

        Sólo toma campos FileField/ImageField de modelos propios. Ajustar a medida
        que se agreguen nuevos campos de archivo.
        """
        import os

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
        for root, dirs, files in os.walk(media_root):
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
