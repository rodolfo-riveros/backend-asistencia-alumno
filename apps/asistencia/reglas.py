"""Reglas de negocio puras (sin base de datos). Ver sección 6 de la especificación."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

P, T, F, J = "P", "T", "F", "J"
ESTADOS = (P, T, F, J)


@dataclass(frozen=True)
class ReglaHora:
    hora_ingreso: time
    tolerancia_min: int
    hora_limite_falta: time


@dataclass(frozen=True)
class EstadoCalculado:
    estado: str
    fuera_de_hora: bool  # pasó la hora límite: se marca T pero con advertencia


def _sumar_min(t: time, minutos: int) -> time:
    return (datetime.combine(date(2000, 1, 1), t) + timedelta(minutes=minutos)).time()


def estado_por_hora(hora: time, regla: ReglaHora) -> EstadoCalculado:
    """Regla 1: P hasta ingreso + tolerancia (incluye todo ese minuto), luego T.

    Con ingreso 7:45 y tolerancia 10 → P hasta 7:55:59, T desde 7:56:00.
    """
    tarde_desde = _sumar_min(regla.hora_ingreso, regla.tolerancia_min + 1)
    if hora < tarde_desde:
        return EstadoCalculado(P, False)
    return EstadoCalculado(T, hora > regla.hora_limite_falta)


def porcentaje_asistencia(presentes: int, tardes: int, justificados: int, dias_habiles: int) -> Decimal | None:
    """Regla 7: (P + T + J) ÷ días hábiles × 100, con 1 decimal."""
    if dias_habiles <= 0:
        return None
    valor = Decimal(presentes + tardes + justificados) * 100 / Decimal(dias_habiles)
    return valor.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def formatear_porcentaje(valor: Decimal | float | None) -> str:
    """92.9 → '92,9 %'; 95.0 → '95 %'; None → '—'."""
    if valor is None:
        return "—"
    texto = f"{Decimal(valor).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}"
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto.replace(".", ",") + " %"


def dias_habiles(desde: date, hasta: date, no_lectivos: set[date] | frozenset = frozenset()) -> list[date]:
    """Regla 8: lunes a viernes entre dos fechas (inclusive) menos los días no lectivos."""
    dias = []
    actual = desde
    while actual <= hasta:
        if actual.weekday() < 5 and actual not in no_lectivos:
            dias.append(actual)
        actual += timedelta(days=1)
    return dias


def es_alerta_riesgo(faltas: int, tardanzas: int, umbral_faltas: int = 3, umbral_tardanzas: int = 4) -> bool:
    """Regla 9: 3 o más faltas o 4 o más tardanzas en el mes."""
    return faltas >= umbral_faltas or tardanzas >= umbral_tardanzas


def validar_marcado_en(
    marcado_en: datetime | None,
    ahora: datetime,
    pasado: timedelta = timedelta(hours=12),
    futuro: timedelta = timedelta(minutes=5),
) -> tuple[datetime, bool]:
    """Regla 11: acepta la hora del dispositivo si está entre −12 h y +5 min del servidor.

    Devuelve (hora_valida, hora_corregida).
    """
    if marcado_en is None or not (ahora - pasado <= marcado_en <= ahora + futuro):
        return ahora, True
    return marcado_en, False


def nueva_marca_gana(
    estado_actual: str,
    marcado_actual: datetime,
    actual_desde_panel: bool,
    marcado_nuevo: datetime,
    nueva_desde_panel: bool = False,
) -> tuple[bool, str | None]:
    """Conflictos (sección 8.4): gana la marca más reciente, salvo que una J
    creada en el panel nunca se pisa desde la app.

    Devuelve (gana, codigo_rechazo).
    """
    if estado_actual == J and actual_desde_panel and not nueva_desde_panel:
        return False, "JUSTIFICADO_POR_DIRECCION"
    if marcado_nuevo < marcado_actual:
        return False, "MARCA_ANTIGUA"
    return True, None


def estado_seccion(total: int, registrados: int) -> str:
    """'COMPLETA' | 'EN_CURSO' | 'PENDIENTE' para la tarjeta de la sección."""
    if total > 0 and registrados >= total:
        return "COMPLETA"
    if registrados == 0:
        return "PENDIENTE"
    return "EN_CURSO"


ESTADO_SECCION_TEXTO = {"COMPLETA": "Completa", "EN_CURSO": "En curso", "PENDIENTE": "Pendiente"}
