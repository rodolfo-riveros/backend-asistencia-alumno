from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from apps.asistencia import reglas

REGLA = reglas.ReglaHora(time(7, 45), 10, time(9, 45))


@pytest.mark.parametrize(
    "hora, esperado",
    [
        (time(7, 30), "P"),
        (time(7, 45), "P"),
        (time(7, 55), "P"),
        (time(7, 55, 59), "P"),
        (time(7, 56), "T"),
        (time(9, 45), "T"),
    ],
)
def test_estado_por_hora(hora, esperado):
    assert reglas.estado_por_hora(hora, REGLA).estado == esperado


def test_despues_de_hora_limite_es_tarde_con_advertencia():
    r = reglas.estado_por_hora(time(9, 46), REGLA)
    assert r.estado == "T" and r.fuera_de_hora is True
    assert reglas.estado_por_hora(time(8, 0), REGLA).fuera_de_hora is False


def test_porcentaje_asistencia():
    assert reglas.porcentaje_asistencia(12, 1, 0, 14) == Decimal("92.9")
    assert reglas.porcentaje_asistencia(19, 0, 1, 20) == Decimal("100.0")
    assert reglas.porcentaje_asistencia(0, 0, 0, 0) is None


def test_formatear_porcentaje_con_coma():
    assert reglas.formatear_porcentaje(Decimal("92.9")) == "92,9 %"
    assert reglas.formatear_porcentaje(Decimal("95.0")) == "95 %"
    assert reglas.formatear_porcentaje(None) == "—"


def test_dias_habiles_excluye_fines_de_semana_y_feriados():
    # Octubre 2026: 1 = jueves. Del 5 (lun) al 9 (vie) con feriado el 8.
    dias = reglas.dias_habiles(date(2026, 10, 3), date(2026, 10, 11), {date(2026, 10, 8)})
    assert dias == [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 9)]


def test_porcentaje_sobre_dias_habiles_sin_feriados():
    habiles = reglas.dias_habiles(date(2026, 10, 1), date(2026, 10, 31), {date(2026, 10, 8)})
    assert len(habiles) == 21
    assert reglas.porcentaje_asistencia(19, 1, 0, len(habiles)) == Decimal("95.2")


@pytest.mark.parametrize(
    "faltas, tardanzas, alerta",
    [(2, 3, False), (3, 0, True), (0, 4, True), (2, 4, True)],
)
def test_alerta_de_riesgo(faltas, tardanzas, alerta):
    assert reglas.es_alerta_riesgo(faltas, tardanzas) is alerta


def test_validar_marcado_en():
    ahora = datetime(2026, 10, 6, 13, 0, tzinfo=timezone.utc)
    assert reglas.validar_marcado_en(ahora - timedelta(hours=11), ahora) == (ahora - timedelta(hours=11), False)
    assert reglas.validar_marcado_en(ahora + timedelta(minutes=4), ahora)[1] is False
    assert reglas.validar_marcado_en(ahora - timedelta(hours=13), ahora) == (ahora, True)
    assert reglas.validar_marcado_en(ahora + timedelta(minutes=6), ahora) == (ahora, True)
    assert reglas.validar_marcado_en(None, ahora) == (ahora, True)


def test_conflictos_gana_la_mas_reciente_salvo_j_de_panel():
    t1 = datetime(2026, 10, 6, 12, 50, tzinfo=timezone.utc)
    t2 = t1 + timedelta(minutes=5)
    assert reglas.nueva_marca_gana("P", t1, False, t2) == (True, None)
    assert reglas.nueva_marca_gana("P", t2, False, t1) == (False, "MARCA_ANTIGUA")
    assert reglas.nueva_marca_gana("J", t1, True, t2) == (False, "JUSTIFICADO_POR_DIRECCION")
    assert reglas.nueva_marca_gana("J", t1, True, t2, nueva_desde_panel=True) == (True, None)


def test_estado_seccion():
    assert reglas.estado_seccion(28, 28) == "COMPLETA"
    assert reglas.estado_seccion(27, 18) == "EN_CURSO"
    assert reglas.estado_seccion(30, 0) == "PENDIENTE"
