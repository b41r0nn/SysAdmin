"""
Management command para sincronizar equipos desde OCS.

Uso:
    python manage.py sync_ocs
    python manage.py sync_ocs --force
    python manage.py sync_ocs --verbose
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from yule.sync import sincronizar_equipos_ocs

User = get_user_model()


class Command(BaseCommand):
    help = "Sincroniza equipos desde OCS Inventory NG"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Fuerza sincronización aunque no haya pasado la frecuencia mínima",
        )
        parser.add_argument(
            "--user",
            type=str,
            default="system",
            help="Usuario a registrar en los logs (default: 'system')",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        username = options.get("user", "system")

        # Obtener usuario o usar None
        usuario = None
        if username != "system":
            try:
                usuario = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"Usuario '{username}' no encontrado. Usando None.")
                )

        self.stdout.write(self.style.SUCCESS("Iniciando sincronización OCS..."))

        log, mensaje = sincronizar_equipos_ocs(usuario=usuario, force=force)

        if log.fue_exitosa:
            self.stdout.write(self.style.SUCCESS(f"✓ {mensaje}"))
        else:
            self.stdout.write(self.style.ERROR(f"✗ {mensaje}"))

        # Detalles
        self.stdout.write("")
        self.stdout.write(f"Estado: {log.get_estado_display()}")
        self.stdout.write(f"Equipos detectados: {log.equipos_detectados}")
        self.stdout.write(f"  - Nuevos: {log.equipos_nuevos}")
        self.stdout.write(f"  - Actualizados: {log.equipos_actualizados}")
        self.stdout.write(f"  - Desaparecidos: {log.equipos_desaparecidos}")
        if log.duracion_segundos:
            self.stdout.write(f"Duración: {log.duracion_segundos}s")

        if log.mensaje_error:
            self.stdout.write(self.style.WARNING(f"Mensaje: {log.mensaje_error}"))
