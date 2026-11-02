"""python manage.py cerrar_dia [--fecha AAAA-MM-DD]

Programar a las 23:59 (Programador de tareas de Windows o cron en Linux).
"""

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.asistencia.servicios import cerrar_dia
from apps.comun.fechas import hoy_lima


class Command(BaseCommand):
    help = "Cierra las sesiones del día y marca F a los estudiantes sin registrar."

    def add_arguments(self, parser):
        parser.add_argument("--fecha", help="AAAA-MM-DD (por defecto, hoy en Lima)")

    def handle(self, *args, **opts):
        try:
            fecha = datetime.strptime(opts["fecha"], "%Y-%m-%d").date() if opts["fecha"] else hoy_lima()
        except ValueError:
            raise CommandError("Fecha inválida. Usa AAAA-MM-DD.")
        r = cerrar_dia(fecha)
        if r["omitido"]:
            self.stdout.write(f"{fecha}: no se cerró ({r['omitido']}).")
        else:
            self.stdout.write(self.style.SUCCESS(
                f"{fecha}: {r['sesiones']} sesiones cerradas, {r['faltas_creadas']} faltas automáticas."
            ))
