from django.core.management.base import BaseCommand

from notificaciones.services import procesar_cola_email


class Command(BaseCommand):
    help = "Despacha la cola de emails (patrón GLPI: cola + cron). Reintenta hasta 5 veces."

    def handle(self, *args, **options):
        total, enviados, fallos, quedan = procesar_cola_email()
        self.stdout.write(
            self.style.SUCCESS(
                f"Emails: {enviados} enviados, {fallos} con error "
                f"(procesados {total}, quedan {quedan} en cola)."
            )
        )