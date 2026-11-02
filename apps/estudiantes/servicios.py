"""Servicios de estudiantes compartidos por el panel y la importación."""

from apps.comun.fechas import hoy_lima

from .models import Carnet, Matricula


def matricular(estudiante, seccion, anio):
    """Crea o mueve la matrícula del año y asegura un carnet activo."""
    matricula = Matricula.objects.filter(estudiante=estudiante, anio_escolar=anio).first()
    if matricula is None:
        alta = min(max(hoy_lima(), anio.fecha_inicio), anio.fecha_fin)
        matricula = Matricula.objects.create(estudiante=estudiante, seccion=seccion, anio_escolar=anio, fecha_alta=alta)
    elif matricula.seccion_id != seccion.id or matricula.estado != Matricula.Estado.ACTIVA:
        matricula.seccion = seccion
        matricula.estado = Matricula.Estado.ACTIVA
        matricula.fecha_baja = None
        matricula.save()
    if not estudiante.activo:
        estudiante.activo = True
        estudiante.save(update_fields=["activo", "actualizado_en"])
    if not Carnet.objects.filter(estudiante=estudiante, estado=Carnet.Estado.ACTIVO).exists():
        Carnet.emitir(estudiante)
    return matricula
