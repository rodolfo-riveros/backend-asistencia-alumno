"""Agregados del panel: dashboard del día y reportes. Los usan las vistas y los exportes.

% de asistencia (regla 7) = (P + T + J) ÷ días registrados, con 1 decimal.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db.models import Count, Q

from apps.academico.models import Grado, Seccion
from apps.asistencia import reglas
from apps.asistencia.models import Registro
from apps.comun.fechas import MESES_CORTOS, sin_tildes
from apps.estudiantes.models import Matricula
from apps.institucion.models import AnioEscolar, Configuracion, DiaNoLectivo

ESTADOS = reglas.ESTADOS  # P, T, F, J


def pct(p: int, t: int, j: int, registrados: int):
    return reglas.porcentaje_asistencia(p, t, j, registrados)


def secciones_del_anio(anio, turno: str | None = None):
    qs = Seccion.objects.filter(anio_escolar=anio).select_related("grado__nivel", "turno", "tutor")
    return qs.filter(turno__nombre=turno) if turno else qs


def _matriculas_en(fecha: date):
    """Matrículas que cuentan ese día: activas o dadas de baja después de esa fecha."""
    return Matricula.objects.filter(fecha_alta__lte=fecha).filter(
        Q(estado=Matricula.Estado.ACTIVA) | Q(fecha_baja__gt=fecha)
    )


def dias_habiles(anio: AnioEscolar, desde: date, hasta: date) -> list[date]:
    desde, hasta = max(desde, anio.fecha_inicio), min(hasta, anio.fecha_fin)
    if hasta < desde:
        return []
    no_lectivos = set(DiaNoLectivo.objects.filter(anio_escolar=anio, fecha__range=(desde, hasta)).values_list("fecha", flat=True))
    return reglas.dias_habiles(desde, hasta, no_lectivos)


# ---------------------------------------------------------------------------- dashboard del día
@dataclass
class FilaSeccion:
    seccion: Seccion
    total: int = 0
    p: int = 0
    t: int = 0
    f: int = 0
    j: int = 0
    pendientes: list = field(default_factory=list)  # nombres cortos de los sin registrar

    @property
    def registrados(self):
        return self.p + self.t + self.f + self.j

    @property
    def sin_registrar(self):
        return max(self.total - self.registrados, 0)

    @property
    def estado(self):
        """COMPLETA | EN_CURSO | SIN_INICIAR"""
        e = reglas.estado_seccion(self.total, self.registrados)
        return "SIN_INICIAR" if e == "PENDIENTE" else e

    @property
    def avance(self):
        return round(self.registrados * 100 / self.total) if self.total else 0


def resumen_dia(fecha: date, turno: str | None = None) -> dict:
    anio = AnioEscolar.activo_actual()
    secciones = list(secciones_del_anio(anio, turno))
    filas = {s.id: FilaSeccion(s) for s in secciones}

    totales = dict(
        _matriculas_en(fecha).filter(seccion__in=secciones).values_list("seccion_id").annotate(n=Count("id")).order_by()
    )
    for sid, n in totales.items():
        filas[sid].total = n

    marcados = defaultdict(set)
    for sid, mid, estado in Registro.objects.filter(
        sesion__fecha=fecha, sesion__bloque_clave=0, sesion__seccion__in=secciones
    ).values_list("sesion__seccion_id", "matricula_id", "estado"):
        setattr(filas[sid], estado.lower(), getattr(filas[sid], estado.lower()) + 1)
        marcados[sid].add(mid)

    for fila in filas.values():
        if fila.sin_registrar:
            faltan = (
                _matriculas_en(fecha).filter(seccion=fila.seccion).exclude(id__in=marcados[fila.seccion.id])
                .select_related("estudiante").order_by("estudiante__apellido_paterno", "estudiante__apellido_materno")
            )
            fila.pendientes = [
                f"{m.estudiante.apellido_paterno} {m.estudiante.apellido_materno[:1]}.".strip() for m in faltan
            ]

    lista = sorted(filas.values(), key=lambda x: (x.seccion.grado.orden, x.seccion.grado.numero, x.seccion.letra))
    k = {e: sum(getattr(x, e.lower()) for x in lista) for e in ESTADOS}
    total = sum(x.total for x in lista)
    registrados = sum(x.registrados for x in lista)

    por_grado = defaultdict(lambda: [0, 0, 0, 0])  # P, T, J, registrados
    for x in lista:
        g = por_grado[x.seccion.grado]
        g[0] += x.p
        g[1] += x.t
        g[2] += x.j
        g[3] += x.registrados
    grados = [
        {"grado": g, "porcentaje": pct(v[0], v[1], v[2], v[3]), "registrados": v[3]}
        for g, v in sorted(por_grado.items(), key=lambda it: (it[0].orden, it[0].numero))
    ]

    return {
        "fecha": fecha,
        "secciones": lista,
        "total": total,
        "registrados": registrados,
        "sin_registrar": total - registrados,
        "secciones_incompletas": sum(1 for x in lista if x.sin_registrar),
        "presentes": k["P"], "tardes": k["T"], "faltas": k["F"], "justificados": k["J"],
        "porcentaje": pct(k["P"], k["T"], k["J"], registrados),
        "por_grado": grados,
    }


def ultimos_dias(fecha: date, n: int = 15, turno: str | None = None) -> list[dict]:
    """% de asistencia y de tardanzas de los últimos n días hábiles (hasta la fecha)."""
    anio = AnioEscolar.activo_actual()
    dias = dias_habiles(anio, fecha - timedelta(days=n * 2 + 14), fecha)[-n:]
    conteo = defaultdict(lambda: defaultdict(int))
    qs = Registro.objects.filter(sesion__fecha__in=dias, sesion__bloque_clave=0)
    if turno:
        qs = qs.filter(sesion__seccion__turno__nombre=turno)
    for d, estado, c in qs.values_list("sesion__fecha", "estado").annotate(c=Count("id")).order_by():
        conteo[d][estado] = c
    salida = []
    for d in dias:
        c = conteo[d]
        reg = sum(c.values())
        salida.append({
            "fecha": d,
            "texto": f"{d.day} {MESES_CORTOS[d.month - 1]}",
            "registrados": reg,
            "asistencia": pct(c["P"], c["T"], c["J"], reg),
            "tardanzas": reglas.porcentaje_asistencia(c["T"], 0, 0, reg) if reg else None,
        })
    return salida


def grafico_dias(dias: list[dict]) -> dict:
    """Coordenadas SVG como en el diseño: asistencia 85–100 % y tardanzas 0–10 % (escala propia)."""
    if not dias:
        return {"asistencia": "", "tardanzas": "", "ultimo": None, "etiquetas": []}
    paso = 510 / max(len(dias) - 1, 1)

    def x(i):
        return 40 + i * paso

    def y_a(v):
        return 20 + (100 - min(max(float(v), 85), 100)) * 12

    def y_t(v):
        return 200 - min(max(float(v), 0), 10) * 18

    asis = [(x(i), y_a(d["asistencia"])) for i, d in enumerate(dias) if d["asistencia"] is not None]
    tard = [(x(i), y_t(d["tardanzas"])) for i, d in enumerate(dias) if d["tardanzas"] is not None]
    medio = len(dias) // 2
    etiquetas = [(40, dias[0]["texto"]), (x(medio) - 20, dias[medio]["texto"]), (505, dias[-1]["texto"])]
    return {
        "asistencia": " ".join(f"{a:.1f},{b:.1f}" for a, b in asis),
        "tardanzas": " ".join(f"{a:.1f},{b:.1f}" for a, b in tard),
        "ultimo": asis[-1] if asis else None,
        "etiquetas": etiquetas if len(dias) > 2 else etiquetas[:1],
    }


# ---------------------------------------------------------------------------- reportes del mes
@dataclass
class FilaEstudiante:
    matricula: Matricula
    celdas: list = field(default_factory=list)  # estado o None por día hábil
    p: int = 0
    t: int = 0
    f: int = 0
    j: int = 0

    @property
    def registrados(self):
        return self.p + self.t + self.f + self.j

    @property
    def porcentaje(self):
        return pct(self.p, self.t, self.j, self.registrados)

    @property
    def nombre(self):
        e = self.matricula.estudiante
        return f"{e.apellidos}, {e.nombres}"


def _rango_mes(anio_n: int, mes: int):
    primero = date(anio_n, mes, 1)
    ultimo = (date(anio_n + (mes == 12), mes % 12 + 1, 1)) - timedelta(days=1)
    return primero, ultimo


def matriz_mensual(anio_n: int, mes: int, hoy: date, seccion=None, grado=None, q: str = "") -> dict:
    """Matriz estudiante × días hábiles + totales y % (Resumen mensual, % por estudiante y Alertas)."""
    anio = AnioEscolar.activo_actual()
    primero, ultimo = _rango_mes(anio_n, mes)
    dias = dias_habiles(anio, primero, min(ultimo, hoy))

    matriculas = Matricula.objects.filter(anio_escolar=anio, fecha_alta__lte=ultimo).filter(
        Q(estado=Matricula.Estado.ACTIVA) | Q(fecha_baja__gte=primero)
    ).select_related("estudiante", "seccion__grado")
    if seccion:
        matriculas = matriculas.filter(seccion=seccion)
    if grado:
        matriculas = matriculas.filter(seccion__grado=grado)
    matriculas = matriculas.order_by(
        "seccion__grado__numero", "seccion__letra", "estudiante__apellido_paterno",
        "estudiante__apellido_materno", "estudiante__nombres",
    )
    if q:
        partes = sin_tildes(q).split()
        matriculas = [
            m for m in matriculas
            if all(p in sin_tildes(f"{m.estudiante.apellidos} {m.estudiante.nombres} {m.estudiante.codigo_estudiante}") for p in partes)
        ]
    filas = {m.id: FilaEstudiante(m) for m in matriculas}

    estados_dia = defaultdict(dict)
    for mid, d, estado in Registro.objects.filter(
        matricula_id__in=list(filas), sesion__bloque_clave=0, sesion__fecha__range=(primero, ultimo)
    ).values_list("matricula_id", "sesion__fecha", "estado"):
        estados_dia[mid][d] = estado

    indice = set(dias)
    for mid, fila in filas.items():
        for d in dias:
            fila.celdas.append(estados_dia[mid].get(d))
        for d, estado in estados_dia[mid].items():
            if d in indice:
                setattr(fila, estado.lower(), getattr(fila, estado.lower()) + 1)

    config = Configuracion.obtener()
    lista = list(filas.values())
    riesgo = [
        x for x in lista if reglas.es_alerta_riesgo(x.f, x.t, config.umbral_faltas, config.umbral_tardanzas)
    ]
    riesgo.sort(key=lambda x: (-x.f, -x.t))
    porcentajes = [float(x.porcentaje) for x in lista if x.porcentaje is not None]
    promedio = round(sum(porcentajes) / len(porcentajes), 1) if porcentajes else None

    return {
        "dias": dias,
        "filas": lista,
        "riesgo": riesgo,
        "promedio": promedio,
        "umbral_faltas": config.umbral_faltas,
        "umbral_tardanzas": config.umbral_tardanzas,
    }


def diario_seccion(seccion, fecha: date) -> list[dict]:
    """Diario por sección: cada estudiante con su registro del día."""
    registros = {
        r.matricula_id: r
        for r in Registro.objects.filter(sesion__seccion=seccion, sesion__fecha=fecha, sesion__bloque_clave=0)
        .select_related("justificacion", "marcado_por")
    }
    filas = []
    for m in _matriculas_en(fecha).filter(seccion=seccion).select_related("estudiante").order_by(
        "estudiante__apellido_paterno", "estudiante__apellido_materno", "estudiante__nombres"
    ):
        r = registros.get(m.id)
        jus = getattr(r, "justificacion", None) if r else None
        filas.append({"matricula": m, "registro": r, "justificacion": jus})
    return filas


def grados_activos():
    return Grado.objects.filter(nivel__activo=True).select_related("nivel")
