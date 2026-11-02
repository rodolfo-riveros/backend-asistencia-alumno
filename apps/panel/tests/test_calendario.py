"""Feriados nacionales automáticos, días propios de la I.E. y carnet con logo + QR."""

from datetime import date, timedelta

import pytest
from django.test import Client

from apps.institucion import feriados
from apps.institucion.models import AnioEscolar, DiaNoLectivo
from conftest import crear_usuario

pytestmark = pytest.mark.django_db


def cliente(usuario):
    c = Client()
    c.force_login(usuario)
    return c


@pytest.mark.parametrize("anio, pascua", [(2024, date(2024, 3, 31)), (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28)), (2030, date(2030, 4, 21))])
def test_semana_santa_se_calcula_cada_anio(anio, pascua):
    assert feriados.domingo_de_pascua(anio) == pascua
    nombres = dict(feriados.feriados_nacionales(anio))
    assert nombres[pascua - timedelta(days=3)] == "Jueves Santo"
    assert nombres[pascua - timedelta(days=2)] == "Viernes Santo"


def test_solo_registra_los_de_lunes_a_viernes_en_clases():
    anio = AnioEscolar.objects.create(anio=2027, fecha_inicio=date(2027, 3, 15), fecha_fin=date(2027, 12, 17))
    n = feriados.sincronizar(anio)
    fechas = set(DiaNoLectivo.objects.filter(anio_escolar=anio).values_list("fecha", flat=True))
    assert date(2027, 1, 1) not in fechas  # antes de clases
    assert date(2027, 3, 25) in fechas and date(2027, 3, 26) in fechas  # Semana Santa 2027
    assert date(2027, 8, 30) in fechas and date(2027, 12, 25) not in fechas  # sábado
    assert all(f.weekday() < 5 for f in fechas)
    assert feriados.sincronizar(anio) == 0 and len(fechas) == n  # no duplica


def test_no_pisa_un_dia_ya_registrado():
    anio = AnioEscolar.objects.create(anio=2027, fecha_inicio=date(2027, 3, 15), fecha_fin=date(2027, 12, 17))
    DiaNoLectivo.objects.create(anio_escolar=anio, fecha=date(2027, 7, 28), motivo="VACACIONES", descripcion="Vacaciones")
    feriados.sincronizar(anio)
    assert DiaNoLectivo.objects.get(anio_escolar=anio, fecha=date(2027, 7, 28)).motivo == "VACACIONES"


def test_pagina_de_calendario_carga_feriados_y_no_permite_quitarlos(escuela):
    c = cliente(escuela.director)
    html = c.get("/panel/configuracion/calendario/").content.decode()
    assert "Feriados nacionales" in html and "Automático" in html and "Fiestas Patrias" in html
    feriado = DiaNoLectivo.objects.filter(anio_escolar=escuela.anio, motivo="FERIADO").first()
    c.post("/panel/configuracion/calendario/", {"anio": escuela.anio.pk, "accion": "quitar", "dia_id": feriado.pk})
    assert DiaNoLectivo.objects.filter(pk=feriado.pk).exists()


def test_agregar_aniversario_y_quitarlo(escuela):
    c = cliente(escuela.director)
    c.post("/panel/configuracion/calendario/", {
        "anio": escuela.anio.pk, "motivo": "ANIVERSARIO", "desde": "2026-10-14", "descripcion": "45.º aniversario",
    })
    dia = DiaNoLectivo.objects.get(anio_escolar=escuela.anio, fecha=date(2026, 10, 14))
    assert dia.motivo == "ANIVERSARIO"
    c.post("/panel/configuracion/calendario/", {"anio": escuela.anio.pk, "accion": "quitar", "dia_id": dia.pk})
    assert not DiaNoLectivo.objects.filter(pk=dia.pk).exists()


def test_no_se_puede_elegir_feriado_nacional_a_mano(escuela):
    r = cliente(escuela.director).post("/panel/configuracion/calendario/", {
        "anio": escuela.anio.pk, "motivo": "FERIADO", "desde": "2026-10-14",
    })
    assert r.status_code == 200 and not DiaNoLectivo.objects.filter(fecha=date(2026, 10, 14)).exists()


def test_dia_del_maestro_sugerido(escuela):
    c = cliente(escuela.director)
    assert "Día del Maestro" in c.get("/panel/configuracion/calendario/").content.decode()
    c.post("/panel/configuracion/calendario/", {"anio": escuela.anio.pk, "accion": "sugerido", "fecha": "2026-07-06", "descripcion": "Día del Maestro"})
    assert DiaNoLectivo.objects.filter(fecha=date(2026, 7, 6), motivo="OTRO").exists()


def test_anio_nuevo_vacio_y_activado_ya(escuela):
    admin = crear_usuario("admin@demo.edu.pe", "ADMIN", "Ana", "Admin")
    cliente(admin).post("/panel/anio/", {
        "accion": "crear", "anio": 2027, "fecha_inicio": "2027-03-15", "fecha_fin": "2027-12-17",
        "copiar_de": escuela.anio.pk, "copiar": "nada", "cuando": "ahora",
    })
    nuevo = AnioEscolar.objects.get(anio=2027)
    assert nuevo.activo and not nuevo.secciones.exists()
    assert DiaNoLectivo.objects.filter(anio_escolar=nuevo, descripcion="Viernes Santo").exists()


def test_anio_nuevo_rechaza_fin_de_otro_anio(escuela):
    admin = crear_usuario("admin@demo.edu.pe", "ADMIN", "Ana", "Admin")
    r = cliente(admin).post("/panel/anio/", {
        "accion": "crear", "anio": 2027, "fecha_inicio": "2027-03-15", "fecha_fin": "2028-01-10",
        "copiar": "todo", "cuando": "despues",
    })
    assert "Debe ser una fecha de 2027" in r.content.decode() and not AnioEscolar.objects.filter(anio=2027).exists()


def test_carnet_sin_foto_solo_qr(escuela):
    html = cliente(escuela.director).get(f"/panel/carnets/seccion/{escuela.s3b.pk}/").content.decode()
    assert 'class="foto"' not in html and "<svg" in html


def test_carnet_lleva_el_logo_sin_marcar_nada(escuela, monkeypatch):
    monkeypatch.setattr("apps.panel.views.carnets.logo_data_uri", lambda inst: "data:image/png;base64,AAAA")
    html = cliente(escuela.director).get(f"/panel/carnets/seccion/{escuela.s3b.pk}/").content.decode()
    assert 'class="logo" src="data:image/png;base64,AAAA"' in html
