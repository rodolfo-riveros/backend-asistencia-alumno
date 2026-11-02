"""Feriados nacionales del Perú calculados para cualquier año (incluye Semana Santa).

Las fechas fijas siguen la ley vigente (D. Leg. 713 y modificatorias: 7 jun, 23 jul, 6 ago y 9 dic).
Los feriados regionales, el aniversario de la institución y los días no laborables que decrete el
Gobierno no se pueden calcular: se agregan a mano en Calendario.
"""

from datetime import date, timedelta

FIJOS = [
    (1, 1, "Año Nuevo"),
    (5, 1, "Día del Trabajo"),
    (6, 7, "Batalla de Arica y Día de la Bandera"),
    (6, 29, "San Pedro y San Pablo"),
    (7, 23, "Día de la Fuerza Aérea del Perú"),
    (7, 28, "Fiestas Patrias"),
    (7, 29, "Fiestas Patrias"),
    (8, 6, "Batalla de Junín"),
    (8, 30, "Santa Rosa de Lima"),
    (10, 8, "Combate de Angamos"),
    (11, 1, "Todos los Santos"),
    (12, 8, "Inmaculada Concepción"),
    (12, 9, "Batalla de Ayacucho"),
    (12, 25, "Navidad"),
]

# No son feriados nacionales, pero en los colegios no hay clases: se ofrecen con un clic.
SUGERIDOS_ESCOLARES = [
    (7, 6, "Día del Maestro"),
]


def domingo_de_pascua(anio: int) -> date:
    """Algoritmo gregoriano anónimo (Meeus/Jones/Butcher)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def feriados_nacionales(anio: int) -> list[tuple[date, str]]:
    pascua = domingo_de_pascua(anio)
    dias = [(date(anio, m, d), n) for m, d, n in FIJOS]
    dias += [(pascua - timedelta(days=3), "Jueves Santo"), (pascua - timedelta(days=2), "Viernes Santo")]
    return sorted(dias)


def feriados_en_clases(anio_escolar) -> list[tuple[date, str]]:
    """Los que caen de lunes a viernes dentro de las fechas de clases (los demás no afectan)."""
    return [
        (f, n) for f, n in feriados_nacionales(anio_escolar.anio)
        if f.weekday() < 5 and anio_escolar.fecha_inicio <= f <= anio_escolar.fecha_fin
    ]


def sincronizar(anio_escolar, modelo=None) -> int:
    """Registra los feriados nacionales que falten. No toca los días que ya existen. Devuelve cuántos agregó."""
    if modelo is None:
        from .models import DiaNoLectivo as modelo
    ya = set(modelo.objects.filter(anio_escolar=anio_escolar).values_list("fecha", flat=True))
    nuevos = [
        modelo(anio_escolar=anio_escolar, fecha=f, motivo="FERIADO", descripcion=n)
        for f, n in feriados_en_clases(anio_escolar) if f not in ya
    ]
    modelo.objects.bulk_create(nuevos)
    return len(nuevos)
