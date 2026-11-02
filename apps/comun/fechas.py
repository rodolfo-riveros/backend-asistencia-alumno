"""Fechas y textos en hora de Lima y español (Perú)."""

import unicodedata
from datetime import date, datetime

from django.utils import timezone

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def ahora_lima() -> datetime:
    return timezone.localtime(timezone.now())


def hoy_lima() -> date:
    return ahora_lima().date()


def a_lima(dt: datetime) -> datetime:
    return timezone.localtime(dt)


def fecha_larga(d: date, con_anio: bool = False) -> str:
    """'Martes, 6 de octubre' (o '... de 2026')."""
    texto = f"{DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]}"
    return f"{texto} de {d.year}" if con_anio else texto


def fecha_corta(d: date) -> str:
    """'Jue 17 sep'."""
    return f"{DIAS_CORTOS[d.weekday()]} {d.day} {MESES_CORTOS[d.month - 1]}"


def mes_texto(anio: int, mes: int) -> str:
    """'Septiembre 2026'."""
    return f"{MESES[mes - 1].capitalize()} {anio}"


def hora_texto(dt: datetime | None) -> str | None:
    """'7:52' en hora de Lima."""
    if dt is None:
        return None
    local = a_lima(dt)
    return f"{local.hour}:{local.minute:02d}"


def hora_corta(t) -> str:
    return f"{t.hour}:{t.minute:02d}"


def sin_tildes(texto: str) -> str:
    normal = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in normal if unicodedata.category(c) != "Mn").lower()
