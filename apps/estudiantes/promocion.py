"""Paso de año: matricular a todo un salón en el año siguiente de una sola vez.

Por defecto cada estudiante pasa al grado siguiente (misma letra si existe). Quien repite se
matricula en una sección de su mismo grado y quien no continúa (egresa o se retira) no se matricula.
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import ProtectedError

from apps.academico.models import Grado, Seccion

from .models import Carnet, Matricula

NO_MATRICULAR = "no"


def grado_siguiente(grado: Grado) -> Grado | None:
    return Grado.objects.filter(nivel=grado.nivel, numero__gt=grado.numero).order_by("numero").first()


def es_ultimo_grado(grado: Grado) -> bool:
    return grado_siguiente(grado) is None


def seccion_sugerida(origen: Seccion, anio_destino) -> Seccion | None:
    """Grado siguiente con la misma letra; si no existe, la primera sección de ese grado."""
    siguiente = grado_siguiente(origen.grado)
    if siguiente is None:
        return None
    qs = Seccion.objects.filter(anio_escolar=anio_destino, grado=siguiente)
    return qs.filter(letra=origen.letra).first() or qs.order_by("letra").first()


def seccion_repite(origen: Seccion, anio_destino) -> Seccion | None:
    qs = Seccion.objects.filter(anio_escolar=anio_destino, grado=origen.grado)
    return qs.filter(letra=origen.letra).first() or qs.order_by("letra").first()


@dataclass
class FilaPromocion:
    matricula: Matricula
    destino_actual: Matricula | None  # si ya fue matriculado en el año destino
    sugerida: Seccion | None

    @property
    def valor_inicial(self) -> str:
        if self.destino_actual:
            return str(self.destino_actual.seccion_id)
        return str(self.sugerida.id) if self.sugerida else NO_MATRICULAR


def filas_de(origen: Seccion, anio_destino) -> list[FilaPromocion]:
    sugerida = seccion_sugerida(origen, anio_destino)
    matriculas = list(
        Matricula.objects.filter(seccion=origen, estado=Matricula.Estado.ACTIVA).select_related("estudiante")
        .order_by("estudiante__apellido_paterno", "estudiante__apellido_materno", "estudiante__nombres")
    )
    ya = {
        m.estudiante_id: m
        for m in Matricula.objects.filter(anio_escolar=anio_destino, estudiante__in=[x.estudiante_id for x in matriculas])
        .select_related("seccion__grado")
    }
    return [FilaPromocion(m, ya.get(m.estudiante_id), sugerida) for m in matriculas]


@transaction.atomic
def aplicar(origen: Seccion, anio_destino, decisiones: dict[int, str]) -> dict:
    """decisiones: {matricula_id: seccion_id destino (str) | 'no'}. Faltantes = sugerida.

    Es idempotente: volver a aplicarlo actualiza la matrícula del año destino en lugar de duplicarla.
    """
    validas = {str(s.id): s for s in Seccion.objects.filter(anio_escolar=anio_destino).select_related("grado")}
    resumen = {"promovidos": 0, "repiten": 0, "otra": 0, "no_matriculados": 0, "quitados": 0}
    for fila in filas_de(origen, anio_destino):
        elegido = decisiones.get(fila.matricula.id, fila.valor_inicial)
        if elegido == NO_MATRICULAR or elegido not in validas:
            if fila.destino_actual:
                try:
                    with transaction.atomic():
                        fila.destino_actual.delete()
                except ProtectedError:
                    # Ya tiene asistencia en el año nuevo: se conserva como retirado.
                    fila.destino_actual.estado = Matricula.Estado.RETIRADO
                    fila.destino_actual.fecha_baja = anio_destino.fecha_inicio
                    fila.destino_actual.save(update_fields=["estado", "fecha_baja", "actualizado_en"])
                resumen["quitados"] += 1
            resumen["no_matriculados"] += 1
            continue
        destino = validas[elegido]
        m, _ = Matricula.objects.update_or_create(
            estudiante=fila.matricula.estudiante, anio_escolar=anio_destino,
            defaults={
                "seccion": destino, "estado": Matricula.Estado.ACTIVA, "fecha_baja": None,
                "fecha_alta": anio_destino.fecha_inicio,
            },
        )
        if not Carnet.objects.filter(estudiante=m.estudiante, estado=Carnet.Estado.ACTIVO).exists():
            Carnet.emitir(m.estudiante)
        if destino.grado_id == origen.grado_id:
            resumen["repiten"] += 1
        elif fila.sugerida and destino.grado_id == fila.sugerida.grado_id:
            resumen["promovidos"] += 1
        else:
            resumen["otra"] += 1
    return resumen


def avance(anio_origen, anio_destino) -> list[dict]:
    """Por sección de origen: cuántos ya tienen matrícula en el año destino."""
    filas = []
    for s in Seccion.objects.filter(anio_escolar=anio_origen).select_related("grado__nivel", "tutor"):
        activos = Matricula.objects.filter(seccion=s, estado=Matricula.Estado.ACTIVA)
        total = activos.count()
        hechos = Matricula.objects.filter(
            anio_escolar=anio_destino, estudiante__in=activos.values("estudiante_id")
        ).count()
        filas.append({
            "seccion": s, "total": total, "hechos": hechos, "sugerida": seccion_sugerida(s, anio_destino),
            "egresa": es_ultimo_grado(s.grado),
        })
    return filas
