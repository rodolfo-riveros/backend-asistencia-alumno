import io
from datetime import date

import pytest
from django.core.cache import cache
from django.test import Client
from openpyxl import load_workbook

from apps.asistencia.servicios import aplicar_marca
from apps.reportes import agregados
from conftest import crear_usuario, lima

pytestmark = pytest.mark.django_db
DIA = date(2026, 10, 6)


def marcar(escuela, usuario, alumno, seccion, estado, d=DIA, hora=(7, 50)):
    r = aplicar_marca(
        usuario, matricula_id=alumno.matricula.id, seccion_id=seccion.id, fecha=d, estado=estado,
        marcado_en=lima(d.year, d.month, d.day, *hora),
        justificacion={"motivo": "SALUD"} if estado == "J" else None,
        motivo_cambio="prueba",  # dirección necesita motivo para fechas pasadas
    )
    assert r.resultado == "aplicada", r.codigo
    return r


def cliente(usuario):
    c = Client()
    c.force_login(usuario)
    return c


@pytest.fixture
def con_marcas(escuela):
    marcar(escuela, escuela.marisol, escuela.mateo, escuela.s3b, "P")
    marcar(escuela, escuela.marisol, escuela.luciana, escuela.s3b, "T", hora=(8, 5))
    return escuela


# ------------------------------------------------------------------ dashboard
def test_resumen_del_dia_cuadra_con_los_registros(con_marcas):
    r = agregados.resumen_dia(DIA)
    assert (r["total"], r["registrados"], r["sin_registrar"]) == (3, 2, 1)
    assert (r["presentes"], r["tardes"], r["faltas"], r["justificados"]) == (1, 1, 0, 0)
    assert float(r["porcentaje"]) == 100.0  # (P + T + J) ÷ registrados
    por_seccion = {x.seccion.letra: x for x in r["secciones"]}
    assert por_seccion["B"].estado == "COMPLETA"
    assert por_seccion["C"].estado == "SIN_INICIAR" and por_seccion["C"].pendientes == ["Rojas C."]
    assert r["secciones_incompletas"] == 1
    assert [float(g["porcentaje"]) for g in r["por_grado"] if g["porcentaje"] is not None] == [100.0]


def test_filtro_por_turno(con_marcas):
    assert agregados.resumen_dia(DIA, "TARDE")["total"] == 0
    assert agregados.resumen_dia(DIA, "MANANA")["total"] == 3


def test_ultimos_dias_habiles_excluye_feriados(con_marcas):
    dias = agregados.ultimos_dias(date(2026, 10, 9), 5)
    fechas = [d["fecha"] for d in dias]
    assert date(2026, 10, 8) not in fechas and fechas[-1] == date(2026, 10, 9)
    dia6 = next(d for d in dias if d["fecha"] == DIA)
    assert float(dia6["asistencia"]) == 100.0 and float(dia6["tardanzas"]) == 50.0
    assert agregados.grafico_dias(dias)["asistencia"]


# ------------------------------------------------------------------ mensual
def test_matriz_mensual_y_alerta_de_riesgo(escuela):
    e = escuela
    e.reloj.poner(lima(2026, 10, 9, 18, 0))
    # Mateo: P el 6, F el 7 y el 9 (8 = feriado). 3 faltas → riesgo con umbral 3.
    marcar(e, e.director, e.mateo, e.s3b, "P", d=date(2026, 10, 6))
    marcar(e, e.director, e.mateo, e.s3b, "F", d=date(2026, 10, 7))
    marcar(e, e.director, e.mateo, e.s3b, "F", d=date(2026, 10, 9))
    marcar(e, e.director, e.mateo, e.s3b, "F", d=date(2026, 10, 5))
    m = agregados.matriz_mensual(2026, 10, date(2026, 10, 9), seccion=e.s3b)
    assert date(2026, 10, 8) not in m["dias"]
    fila = next(x for x in m["filas"] if x.matricula == e.mateo.matricula)
    assert (fila.p, fila.f, fila.registrados) == (1, 3, 4)
    assert float(fila.porcentaje) == 25.0
    assert [x.matricula for x in m["riesgo"]] == [e.mateo.matricula]
    # Búsqueda sin tildes
    assert len(agregados.matriz_mensual(2026, 10, date(2026, 10, 9), seccion=e.s3b, q="huaman")["filas"]) == 1


# ------------------------------------------------------------------ panel y exportes
def test_dashboard_y_exportes(con_marcas):
    c = cliente(con_marcas.director)
    html = c.get("/panel/?fecha=2026-10-06").content.decode()
    assert "Asistencia de hoy" in html and "2 de 3 registrados" in html and "Recordar a los docentes" in html
    assert "Rojas C." in html
    # Números para CSS/SVG con punto decimal aunque el idioma sea es-PE (si no, la barra no se dibuja).
    assert 'style="width:100.0%"' in html and "width:100,0%" not in html

    parcial = c.get("/panel/?fecha=2026-10-06", HTTP_HX_REQUEST="true").content.decode()
    assert "<aside" not in parcial and "2 de 3 registrados" in parcial

    r = c.get("/panel/?fecha=2026-10-06&formato=xlsx")
    libro = load_workbook(io.BytesIO(r.content))
    hoja = libro["Por sección"]
    filas = [[c.value for c in f] for f in hoja.iter_rows(min_row=14, max_row=15)]
    assert filas[0][0].startswith("3.º B") and filas[0][2:8] == [2, 2, 1, 1, 0, 0]

    assert "Imprimir / Guardar como PDF" in c.get("/panel/?fecha=2026-10-06&formato=imprimir").content.decode()


def test_reportes_cuatro_pestanas_y_excel_con_colores(con_marcas):
    e = con_marcas
    c = cliente(e.director)
    for tab in ("diario", "mensual", "estudiantes", "alertas"):
        r = c.get(f"/panel/reportes/?tab={tab}&mes=2026-10&seccion={e.s3b.pk}&fecha=2026-10-06")
        assert r.status_code == 200, tab
        assert c.get(f"/panel/reportes/?tab={tab}&mes=2026-10&seccion={e.s3b.pk}&formato=imprimir").status_code == 200
        x = c.get(f"/panel/reportes/?tab={tab}&mes=2026-10&seccion={e.s3b.pk}&fecha=2026-10-06&formato=xlsx")
        assert x["Content-Type"].startswith("application/vnd.openxmlformats")
        load_workbook(io.BytesIO(x.content))

    x = c.get(f"/panel/reportes/?tab=mensual&mes=2026-10&seccion={e.s3b.pk}&formato=xlsx")
    hoja = load_workbook(io.BytesIO(x.content)).active
    celdas = {cel.value: cel.fill.fgColor.rgb for fila in hoja.iter_rows(min_row=6) for cel in fila if cel.value in ("P", "T")}
    assert celdas["P"].endswith("E3F1E8") and celdas["T"].endswith("FBEEDB")


def test_docente_no_entra_a_reportes(escuela):
    assert cliente(escuela.marisol).get("/panel/reportes/").status_code == 403


# ------------------------------------------------------------------ recordatorio push
def test_recordar_docentes_una_vez_cada_15_min(escuela, monkeypatch):
    cache.clear()
    enviados = []

    def falso(usuarios, titulo, cuerpo, datos=None):
        lista = list(usuarios)
        enviados.append(sorted(u.email for u in lista))
        return {"enviados": len(lista), "sin_app": 0, "errores": 0}

    monkeypatch.setattr("apps.panel.views.dashboard.enviar_push", falso)
    marcar(escuela, escuela.marisol, escuela.mateo, escuela.s3b, "P")  # 3.º B incompleta, 5.º C sin iniciar
    c = cliente(escuela.director)

    r = c.post("/panel/recordar/", follow=True)
    assert "Recordatorio enviado a 2 docentes" in r.content.decode()
    assert enviados == [["m.quispe@ie-ejemplo.edu.pe", "otro@ie-ejemplo.edu.pe"]]

    r = c.post("/panel/recordar/", follow=True)
    assert "Podrás enviar otro en" in r.content.decode() and len(enviados) == 1

    escuela.reloj.poner(lima(2026, 10, 6, 8, 6))  # 16 minutos después
    cache.clear()  # el caché en memoria no sabe del reloj simulado: equivale al vencimiento
    c.post("/panel/recordar/")
    assert len(enviados) == 2


def test_enviar_push_sin_token_o_token_invalido(escuela, monkeypatch):
    from apps.cuentas import push

    escuela.marisol.expo_push_token = "ExponentPushToken[abc123]"
    escuela.marisol.save()
    escuela.otro.expo_push_token = "no-es-un-token"
    escuela.otro.save()

    class Ticket:
        def validate_response(self):
            return None

    class ClienteFalso:
        def publish_multiple(self, mensajes):
            assert [m.to for m in mensajes] == ["ExponentPushToken[abc123]"]
            return [Ticket() for _ in mensajes]

    monkeypatch.setattr(push, "PushClient", type("PC", (ClienteFalso,), {"is_exponent_push_token": staticmethod(push.PushClient.is_exponent_push_token)}))
    r = push.enviar_push([escuela.marisol, escuela.otro, crear_usuario("x@x.pe", "DOCENTE")], "t", "c")
    assert r == {"enviados": 1, "sin_app": 2, "errores": 0}
