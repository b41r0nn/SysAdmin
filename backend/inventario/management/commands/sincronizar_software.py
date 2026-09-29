"""Lee el inventario de software de todos los activos vinculados a OCS.

    python manage.py sincronizar_software
    python manage.py sincronizar_software --dry-run
    python manage.py sincronizar_software --verbose
    python manage.py sincronizar_software --activo 24

Se deja para un cron o para un proceso que la llame cada pocas horas. Ver
`inventario/sync_software.py` para qué no se engancha al sync de equipos.
"""
from django.core.management.base import BaseCommand, CommandError

from inventario.models import Activo
from inventario.sync_software import (
    activos_con_equipo_ocs,
    linea_resumen,
    sincronizar_software,
)
from yule.client import build_client, OCSClientException


class Command(BaseCommand):
    help = "Sincroniza el software instalado de los activos con el reporte de OCS."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="No escribe nada: solo consulta OCS y muestra qué leería.",
        )
        parser.add_argument(
            "--activo", type=int, metavar="PK",
            help="Lee solo ese activo, en lugar de toda la flota.",
        )
        parser.add_argument(
            "--incluir-dados-de-baja", action="store_true",
            help="También lee los activos marcados como dado de baja.",
        )
        parser.add_argument(
            "--verbose", action="store_true", help="Una línea por activo.",
        )
        parser.add_argument(
            "--pausa", type=float, default=0.0, metavar="SEGUNDOS",
            help=(
                "Espera entre equipo y equipo. OCS es un servidor interno: 24 "
                "requests seguidos se leen como un barrido, no como el trabajo "
                "normal de los agentes. 0 para no pausar."
            ),
        )

    def handle(self, *args, **options):
        # Si OCS no responde, avisarlo antes de arrancar evita 24 fallos
        # idénticos en el log y un resumen que parece un problema de la base.
        try:
            client = build_client()
            if not client.is_configured():
                raise CommandError(
                    "La integración con OCS no está configurada. "
                    "Cargala en Yule › Configuración OCS."
                )
        except OCSClientException as exc:
            raise CommandError(f"El servidor OCS no respondió: {exc}") from exc

        if options["activo"]:
            activos = list(Activo.objects.filter(pk=options["activo"]))
            if not activos:
                raise CommandError(f"No existe el activo {options['activo']}.")
        else:
            activos = list(activos_con_equipo_ocs(options["incluir_dados_de_baja"]))

        if not activos:
            self.stdout.write(
                self.style.WARNING(
                    "Ningún activo tiene un equipo OCS vinculado. "
                    "Vinculalos en Yule o usá la búsqueda por coincidencia."
                )
            )
            return

        verboso = options["verbose"] or options["dry_run"]
        if verboso:
            self.stdout.write(f"Leyendo {len(activos)} activos de OCS...")
        else:
            self.stdout.write("Leyendo software de OCS, puede tardar...")

        def _al_terminar(detalle):
            if not verboso:
                return
            item = detalle[-1]
            etiqueta = {
                "sin_equipo": "sin equipo OCS",
                "no_configurado": "OCS no configurado",
                "error": "OCS no respondió",
            }.get(item["estado"], f"{item['programas']} programas")
            if item["estado"] == "ok":
                if item["cambios"]:
                    etiqueta += f", {item['cambios']} cambios"
                elif "guardadas" in item:
                    etiqueta += f", {item['guardadas']} ya guardadas"
            self.stdout.write(f"  {item['host']:<16} {etiqueta}")

        resumen = sincronizar_software(
            activos=activos,
            dry_run=options["dry_run"],
            on_equipo=_al_terminar if verboso else None,
            pausa=options["pausa"],
        )

        self.stdout.write("")
        prefijo = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(prefijo + linea_resumen(resumen))

        if resumen["fallidos"]:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                f"{resumen['fallidos']} activos no respondieron. "
                "Su inventario guardado quedó intacto, no se marcó nada como desinstalado."
            ))
        if options["dry_run"]:
            self.stdout.write("")
            self.stdout.write("No se escribió nada en la base.")
        else:
            self.stdout.write(f"Total en base: {resumen['guardadas']} filas de software.")
