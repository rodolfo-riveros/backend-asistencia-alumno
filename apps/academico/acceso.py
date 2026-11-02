"""Qué secciones puede ver y marcar cada usuario, según los permisos de su rol.
Nunca confiar en IDs de la app: toda consulta pasa por aquí."""

from django.db.models import Q

from apps.institucion.models import AnioEscolar, Configuracion

from .models import BloqueHorario, Seccion


def ve_todas(usuario) -> bool:
    return usuario.puede("asistencia.todas_las_secciones") or usuario.puede("asistencia.escanear_puerta")


def secciones_visibles(usuario):
    """Secciones del año activo que el usuario puede consultar."""
    anio = AnioEscolar.activo_actual()
    qs = Seccion.objects.filter(anio_escolar=anio).select_related("grado__nivel", "turno", "tutor")
    if ve_todas(usuario):
        return qs
    if usuario.puede("asistencia.pasar_lista") or usuario.puede("estudiantes.ver_historial"):
        return qs.filter(Q(tutor=usuario) | Q(asignaciones__docente=usuario)).distinct()
    return qs.none()


def es_tutor(usuario, seccion) -> bool:
    return seccion.tutor_id == usuario.id


def puede_marcar(usuario, seccion, bloque: BloqueHorario | None = None, metodo: str = "MANUAL") -> bool:
    """Quién puede registrar asistencia en una sección / bloque."""
    if bloque is not None and bloque.seccion_id != seccion.id:
        return False
    if usuario.puede("asistencia.todas_las_secciones"):
        return True
    if bloque is None and metodo == "QR" and usuario.puede("asistencia.escanear_puerta"):
        return True
    if usuario.puede("asistencia.pasar_lista"):
        if bloque is None:
            return es_tutor(usuario, seccion)
        return Configuracion.obtener().permite_bloques and bloque.asignacion.docente_id == usuario.id
    return False


def puede_justificar(usuario, seccion, bloque=None) -> bool:
    return usuario.puede("asistencia.justificar") and puede_marcar(usuario, seccion, bloque)


def puede_ver_apoderado(usuario, seccion) -> bool:
    if not usuario.puede("estudiantes.ver_apoderado"):
        return False
    return usuario.puede("asistencia.todas_las_secciones") or es_tutor(usuario, seccion)
