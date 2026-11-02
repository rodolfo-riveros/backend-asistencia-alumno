"""Año escolar: crear uno nuevo copiando la estructura del anterior."""

from datetime import date

from django.db import transaction

from apps.academico.models import Asignacion, Seccion

from . import feriados as feriados_peru
from .models import AnioEscolar

def anio_anterior(anio: AnioEscolar) -> AnioEscolar | None:
    return AnioEscolar.objects.filter(anio__lt=anio.anio).order_by("-anio").first()


@transaction.atomic
def crear_anio(
    anio: int, fecha_inicio: date, fecha_fin: date, *, copiar_de: AnioEscolar | None = None,
    copiar_secciones=True, copiar_cursos=True, feriados=True, activar=False,
) -> tuple[AnioEscolar, dict]:
    """Crea el año. Devuelve (año, resumen) con lo que se copió."""
    nuevo = AnioEscolar.objects.create(anio=anio, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, activo=activar)
    resumen = {"secciones": 0, "asignaciones": 0, "feriados": 0}

    if copiar_de and copiar_secciones:
        for s in Seccion.objects.filter(anio_escolar=copiar_de).select_related("tutor"):
            nueva, creada = Seccion.objects.get_or_create(
                anio_escolar=nuevo, grado=s.grado, letra=s.letra,
                defaults={
                    "turno": s.turno, "tutor": s.tutor if s.tutor and s.tutor.is_active else None,
                    "aula": s.aula, "capacidad": s.capacidad,
                },
            )
            resumen["secciones"] += creada
            if copiar_cursos:
                for a in Asignacion.objects.filter(seccion=s, docente__is_active=True):
                    _, ok = Asignacion.objects.get_or_create(seccion=nueva, curso=a.curso, defaults={"docente": a.docente})
                    resumen["asignaciones"] += ok

    if feriados:
        resumen["feriados"] = feriados_peru.sincronizar(nuevo)
    return nuevo, resumen
