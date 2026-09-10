from django.core.management.base import BaseCommand

from notificaciones.services import generar_notificaciones_mantenimiento


class Command(BaseCommand):
    help = "Genera notificaciones de mantenimiento para los usuarios con acceso al módulo."

    def handle(self, *args, **options):
        total = generar_notificaciones_mantenimiento()
        self.stdout.write(
            self.style.SUCCESS(f"Notificaciones de mantenimiento creadas: {total}")
        )