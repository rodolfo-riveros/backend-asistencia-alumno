"""python manage.py qr_prueba [--seccion "3B"] [--salida qr_prueba]

Genera PNG con el QR de cada carnet activo para probar el escáner de la app
(mientras no exista la hoja A4 del panel). Incluye un QR inválido.
"""

from pathlib import Path

import segno
from django.core.management.base import BaseCommand, CommandError

from apps.estudiantes.models import Carnet, Matricula
from apps.institucion.models import AnioEscolar


class Command(BaseCommand):
    help = "Genera imágenes QR de prueba para una sección."

    def add_arguments(self, parser):
        parser.add_argument("--seccion", default="3B", help="Grado y letra, ej. 3B")
        parser.add_argument("--salida", default="qr_prueba")

    def handle(self, *args, **opts):
        clave = opts["seccion"].upper().strip()
        if len(clave) < 2 or not clave[0].isdigit():
            raise CommandError("Usa el formato 3B (grado + letra).")
        matriculas = Matricula.objects.filter(
            anio_escolar=AnioEscolar.activo_actual(), estado=Matricula.Estado.ACTIVA,
            seccion__grado__numero=int(clave[0]), seccion__letra=clave[1:],
        ).select_related("estudiante")
        if not matriculas:
            raise CommandError(f"No hay estudiantes en {clave}.")

        carpeta = Path(opts["salida"])
        carpeta.mkdir(parents=True, exist_ok=True)
        for m in matriculas:
            carnet = Carnet.objects.filter(estudiante=m.estudiante, estado=Carnet.Estado.ACTIVO).first()
            if not carnet:
                continue
            nombre = f"{m.estudiante.apellido_paterno}_{m.estudiante.nombres.split()[0]}_{m.estudiante_id}.png"
            segno.make(carnet.contenido_qr, error="m").save(carpeta / nombre, scale=10, dark="#14213D")
        segno.make("AE1.codigo-que-no-existe-000", error="m").save(carpeta / "_invalido.png", scale=10)
        self.stdout.write(self.style.SUCCESS(f"QR generados en {carpeta.resolve()}"))
