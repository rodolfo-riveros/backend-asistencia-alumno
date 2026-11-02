"""Consultas agregadas reutilizadas por la API móvil y (luego) por el panel."""

import calendar
from collections import Counter
from datetime import date

from django.db.models import Count

from apps.asistencia import reglas
from apps.asistencia.models import Estado, Registro, SesionAsistencia
from apps.comun.fechas import fecha_corta
from apps.estudiantes.models import Matricula
from apps.institucion.models import Configuracion, DiaNoLectivo


def contar_estados(registros) -> dict:
    conteo = dict(registros.values_list("estado").annotate(n=Count("id")).order_by())
    return {
        "presentes": conteo.get(Estado.PRESENTE, 0),
        "tardes": conteo.get(Estado.TARDE, 0),
        "faltas": conteo.get(Estado.FALTA, 0),
        "justificados": conteo.get(Estado.JUSTIFICADO, 0),
    }


def resumen_sesion(seccion, fecha: date, bloque=None) -> dict:
    """Contadores de una sección en un día (tarjeta de 'Mis secciones')."""
    total = Matricula.objects.filter(seccion=seccion, estado=Matricula.Estado.ACTIVA).count()
    sesion = SesionAsistencia.objects.filter(
        seccion=seccion, fecha=fecha, bloque_clave=bloque.id if bloque else 0
    ).first()
    conteo = contar_estados(Registro.objects.filter(sesion=sesion)) if sesion else contar_estados(Registro.objects.none())
    registrados = sum(conteo.values())
    estado = reglas.estado_seccion(total, registrados)
    return {
        "total": total,
        **conteo,
        "registrados": registrados,
        "sin_registrar": max(total - registrados, 0),
        "estado": estado,
        "estado_texto": reglas.ESTADO_SECCION_TEXTO[estado],
        "sesion_id": sesion.id if sesion else None,
        "sesion_cerrada": bool(sesion and sesion.estado == SesionAsistencia.EstadoSesion.CERRADA),
    }


def no_lectivos(anio_escolar, desde: date, hasta: date) -> set[date]:
    return set(
        DiaNoLectivo.objects.filter(anio_escolar=anio_escolar, fecha__range=(desde, hasta)).values_list("fecha", flat=True)
    )


def historial_mes(matricula, anio: int, mes: int, hoy: date) -> dict:
    """Pantalla 06: indicadores, calendario y lista de faltas/justificaciones."""
    anio_escolar = matricula.anio_escolar
    primero = date(anio, mes, 1)
    ultimo = date(anio, mes, calendar.monthrange(anio, mes)[1])
    feriados = no_lectivos(anio_escolar, primero, ultimo)

    registros = {
        r.sesion.fecha: r
        for r in Registro.objects.filter(
            matricula=matricula, sesion__bloque__isnull=True, sesion__fecha__range=(primero, ultimo)
        ).select_related("sesion", "justificacion")
    }

    dias = []
    for n in range(1, ultimo.day + 1):
        d = date(anio, mes, n)
        habil = (
            d.weekday() < 5 and d not in feriados and anio_escolar.fecha_inicio <= d <= anio_escolar.fecha_fin
        )
        reg = registros.get(d)
        dias.append({
            "fecha": d.isoformat(),
            "dia": n,
            "dia_semana": d.isoweekday(),
            "habil": habil,
            "futuro": d > hoy,
            "estado": reg.estado if reg and habil else None,
        })

    conteo = Counter(r.estado for r in registros.values())
    p, t, f, j = (conteo.get(x, 0) for x in reglas.ESTADOS)
    # Denominador: días hábiles con registro (los días sin pase de lista no cuentan en contra).
    pct = reglas.porcentaje_asistencia(p, t, j, p + t + f + j)
    config = Configuracion.obtener()

    eventos = []
    for d in sorted(registros, reverse=True):
        r = registros[d]
        if r.estado not in (Estado.FALTA, Estado.JUSTIFICADO):
            continue
        if r.estado == Estado.JUSTIFICADO and hasattr(r, "justificacion"):
            jus = r.justificacion
            detalle = jus.get_motivo_display() + (", con constancia" if jus.foto else "")
            if jus.detalle:
                detalle += f" · {jus.detalle}"
        elif r.estado == Estado.JUSTIFICADO:
            detalle = "Justificado"
        else:
            detalle = "Sin justificar"
        eventos.append({
            "registro_id": r.id,
            "estado": r.estado,
            "estado_original": r.estado_original or None,
            "titulo": "Justificado" if r.estado == Estado.JUSTIFICADO else "Falta",
            "fecha": d.isoformat(),
            "fecha_texto": fecha_corta(d),
            "detalle": detalle,
            "editable": d == hoy,
        })

    return {
        "indicadores": {
            "porcentaje": float(pct) if pct is not None else None,
            "porcentaje_texto": reglas.formatear_porcentaje(pct),
            "presentes": p,
            "tardanzas": t,
            "faltas": f,
            "justificados": j,
            "alerta_riesgo": reglas.es_alerta_riesgo(f, t, config.umbral_faltas, config.umbral_tardanzas),
        },
        "dias": dias,
        "eventos": eventos,
    }
