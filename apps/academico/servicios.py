"""En primaria el tutor suele dictar todas las áreas de su salón."""

from django.db import transaction

from .models import Asignacion, Curso


@transaction.atomic
def tutor_dicta_todo(seccion, anterior=None) -> dict:
    """Asigna al tutor de la sección todos los cursos activos que aún no tienen docente.

    Si se cambió de tutor, los cursos que dictaba el tutor anterior pasan al nuevo
    (los cursos de otros docentes, p. ej. Inglés o Educación Física, no se tocan).
    """
    tutor = seccion.tutor
    if not tutor:
        return {"nuevos": 0, "pasados": 0}
    pasados = 0
    if anterior and anterior != tutor:
        pasados = Asignacion.objects.filter(seccion=seccion, docente=anterior).update(docente=tutor)
    con_docente = set(Asignacion.objects.filter(seccion=seccion).values_list("curso_id", flat=True))
    nuevos = [
        Asignacion(seccion=seccion, curso=c, docente=tutor)
        for c in Curso.objects.filter(activo=True).exclude(pk__in=con_docente)
    ]
    Asignacion.objects.bulk_create(nuevos)
    return {"nuevos": len(nuevos), "pasados": pasados}
