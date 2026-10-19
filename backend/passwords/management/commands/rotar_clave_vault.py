from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from passwords.crypto import build_fernet

# (app_label.Modelo, campo cifrado) que usan build_fernet().
CAMPOS_CIFRADOS = (
    ("passwords.Credencial", "secreto_encriptado"),
    ("administracion.ConfiguracionSistema", "smtp_password_cifrado"),
    ("yule.ConfiguracionYule", "password_cifrada"),
)


class Command(BaseCommand):
    help = (
        "Re-cifra los secretos guardados con PASSWORDS_ENCRYPTION_KEY. "
        "Necesario una vez tras definir la clave (antes se derivaba de SECRET_KEY)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Solo verifica que todo se pueda descifrar; no escribe.",
        )

    def handle(self, *args, **options):
        from django.apps import apps

        if not getattr(settings, "PASSWORDS_ENCRYPTION_KEY", ""):
            raise CommandError("PASSWORDS_ENCRYPTION_KEY no está definida en el entorno.")

        fernet = build_fernet()
        dry_run = options["dry_run"]
        total = 0
        with transaction.atomic():
            for modelo, campo in CAMPOS_CIFRADOS:
                Model = apps.get_model(modelo)
                for obj in Model.objects.exclude(**{campo: ""}):
                    token = getattr(obj, campo).encode()
                    try:
                        nuevo = fernet.rotate(token).decode()
                    except Exception as exc:
                        raise CommandError(
                            f"{modelo} pk={obj.pk}: no se pudo descifrar ({exc.__class__.__name__}). "
                            "No se modificó nada."
                        ) from exc
                    if not dry_run:
                        Model.objects.filter(pk=obj.pk).update(**{campo: nuevo})
                    total += 1
            if not dry_run:
                # Verificación: todo debe descifrar SOLO con la clave nueva.
                from cryptography.fernet import Fernet

                solo_nueva = Fernet(settings.PASSWORDS_ENCRYPTION_KEY.encode())
                for modelo, campo in CAMPOS_CIFRADOS:
                    Model = apps.get_model(modelo)
                    for valor in Model.objects.exclude(**{campo: ""}).values_list(campo, flat=True):
                        solo_nueva.decrypt(valor.encode())

        accion = "verificados" if dry_run else "re-cifrados"
        self.stdout.write(self.style.SUCCESS(f"Secretos {accion}: {total}"))
