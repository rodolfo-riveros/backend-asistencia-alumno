import uuid
from datetime import date, datetime

import pytest

from apps.asistencia.models import Justificacion, Registro, SesionAsistencia
from apps.asistencia.servicios import cerrar_dia
from apps.estudiantes.models import Carnet
from conftest import cliente_de, lima

pytestmark = pytest.mark.django_db

HOY = "2026-10-06"


def marca(e, alumno, estado="P", seccion=None, marcado_en=None, **extra):
    return {
        "uuid_cliente": str(uuid.uuid4()),
        "matricula_id": alumno.matricula.id,
        "seccion_id": (seccion or e.s3b).id,
        "fecha": HOY,
        "estado": estado,
        "metodo": "MANUAL",
        "marcado_en": (marcado_en or lima(2026, 10, 6, 7, 48)).isoformat(),
        **extra,
    }


def enviar(cliente, *marcas):
    r = cliente.post("/api/v1/asistencia/lote/", {"marcas": list(marcas)}, format="json")
    assert r.status_code == 200, r.content
    return r.json()["resultados"]


# ---------------------------------------------------------------- permisos
def test_docente_no_ve_secciones_ajenas(escuela):
    c = cliente_de(escuela.marisol)
    assert c.get(f"/api/v1/secciones/{escuela.s3b.id}/sesion/").status_code == 200
    assert c.get(f"/api/v1/secciones/{escuela.s5c.id}/sesion/").status_code == 403
    assert c.get(f"/api/v1/estudiantes/{escuela.ajeno.estudiante.id}/historial/").status_code == 404

    nombres = [x["nombres"] for x in c.get("/api/v1/estudiantes/?q=").json()["resultados"]]
    assert "Fabián" not in nombres and "Mateo Joaquín" in nombres


def test_docente_no_puede_marcar_en_seccion_ajena(escuela):
    res = enviar(cliente_de(escuela.marisol), marca(escuela, escuela.ajeno, seccion=escuela.s5c))
    assert res[0]["resultado"] == "rechazada" and res[0]["codigo"] == "SIN_PERMISO"
    # Ni mandando su propia sección con una matrícula ajena.
    res = enviar(cliente_de(escuela.marisol), marca(escuela, escuela.ajeno, seccion=escuela.s3b))
    assert res[0]["codigo"] == "MATRICULA_INVALIDA"
    assert not Registro.objects.exists()


def test_auxiliar_no_marca_manual_ni_ve_listas(escuela):
    c = cliente_de(escuela.auxiliar)
    assert enviar(c, marca(escuela, escuela.mateo))[0]["codigo"] == "SIN_PERMISO"
    assert c.get(f"/api/v1/secciones/{escuela.s3b.id}/sesion/").status_code == 403


def test_hoy_muestra_solo_tutorias(escuela):
    data = cliente_de(escuela.marisol).get("/api/v1/movil/hoy/").json()
    assert data["fecha_texto"] == "Martes, 6 de octubre"
    assert [t["seccion_id"] for t in data["tarjetas"]] == [escuela.s3b.id]
    assert data["tarjetas"][0]["estado"] == "PENDIENTE"
    assert data["turno"]["tarde_desde_texto"] == "7:56"


# ---------------------------------------------------------------- lote
def test_lote_es_idempotente(escuela):
    c = cliente_de(escuela.marisol)
    m = marca(escuela, escuela.mateo)
    assert enviar(c, m)[0]["resultado"] == "aplicada"
    segundo = enviar(c, m)[0]
    assert segundo["resultado"] == "duplicada" and segundo["estado_final"] == "P"
    assert Registro.objects.count() == 1
    assert SesionAsistencia.objects.count() == 1


def test_conflicto_gana_la_marca_mas_reciente(escuela):
    c = cliente_de(escuela.marisol)
    reciente = marca(escuela, escuela.mateo, "T", marcado_en=lima(2026, 10, 6, 7, 49))
    antigua = marca(escuela, escuela.mateo, "F", marcado_en=lima(2026, 10, 6, 7, 40))
    enviar(c, reciente)
    res = enviar(c, antigua)[0]
    assert res["resultado"] == "rechazada" and res["codigo"] == "MARCA_ANTIGUA" and res["estado_final"] == "T"


def test_j_de_direccion_no_se_pisa_desde_la_app(escuela):
    from apps.asistencia.servicios import aplicar_marca

    aplicar_marca(
        escuela.director, matricula_id=escuela.mateo.matricula.id, seccion_id=escuela.s3b.id, fecha=date(2026, 10, 6),
        estado="J", marcado_en=lima(2026, 10, 6, 7, 30), origen="PANEL", justificacion={"motivo": "SALUD"},
    )
    res = enviar(cliente_de(escuela.marisol), marca(escuela, escuela.mateo, "F"))[0]
    assert res["codigo"] == "JUSTIFICADO_POR_DIRECCION" and res["estado_final"] == "J"


def test_quitar_marca_y_dia_no_lectivo(escuela):
    c = cliente_de(escuela.marisol)
    enviar(c, marca(escuela, escuela.mateo, "P"))
    res = enviar(c, marca(escuela, escuela.mateo, None, marcado_en=lima(2026, 10, 6, 7, 49)))[0]
    assert res["resultado"] == "aplicada" and not Registro.objects.exists()

    escuela.reloj.poner(lima(2026, 10, 8, 8, 0))  # feriado
    m = marca(escuela, escuela.mateo, marcado_en=lima(2026, 10, 8, 7, 50))
    m["fecha"] = "2026-10-08"
    assert enviar(c, m)[0]["codigo"] == "DIA_NO_LECTIVO"


def test_docente_solo_edita_el_mismo_dia(escuela):
    escuela.reloj.poner(lima(2026, 10, 7, 8, 0))
    res = enviar(cliente_de(escuela.marisol), marca(escuela, escuela.mateo, marcado_en=lima(2026, 10, 7, 7, 50)))[0]
    assert res["codigo"] == "FUERA_DE_FECHA"


def test_hora_del_dispositivo_fuera_de_rango_se_corrige(escuela):
    enviar(cliente_de(escuela.marisol), marca(escuela, escuela.mateo, marcado_en=lima(2026, 10, 6, 7, 56)))
    r = Registro.objects.get()
    assert r.hora_corregida is True and r.marcado_en == lima(2026, 10, 6, 7, 50)


# ---------------------------------------------------------------- escáner
def escanear(cliente, codigo, **extra):
    r = cliente.post("/api/v1/asistencia/escanear/", {"codigo": codigo, **extra}, format="json")
    assert r.status_code == 200, r.content
    return r.json()


def test_escanear_presente_tarde_duplicado_invalido_otra_seccion(escuela):
    c = cliente_de(escuela.marisol)
    qr_mateo = escuela.mateo.carnet.contenido_qr

    escuela.reloj.poner(lima(2026, 10, 6, 7, 55, 30))
    ok = escanear(c, qr_mateo, modo="SECCION", seccion_id=escuela.s3b.id)
    assert ok["resultado"] == "ok" and ok["estado"] == "P" and ok["estudiante"]["nombre_completo"] == "Flores Cusi, Mateo Joaquín"
    # La app guarda este instante en su caché para mostrar la hora en la lista.
    assert ok["fecha"] == "2026-10-06" and datetime.fromisoformat(ok["marcado_en"]) == lima(2026, 10, 6, 7, 55, 30)

    dup = escanear(c, qr_mateo, modo="SECCION", seccion_id=escuela.s3b.id)
    assert dup["resultado"] == "duplicado" and dup["mensaje"] == "Ya registrado a las 7:55"

    escuela.reloj.poner(lima(2026, 10, 6, 7, 56))
    tarde = escanear(c, escuela.luciana.carnet.contenido_qr, modo="SECCION", seccion_id=escuela.s3b.id)
    assert tarde["estado"] == "T" and tarde["mensaje"] == "Tarde registrada"

    assert escanear(c, "AE1.no-existe-este-codigo-123")["resultado"] == "invalido"
    assert escanear(c, "texto cualquiera")["resultado"] == "invalido"

    otra = escanear(c, escuela.ajeno.carnet.contenido_qr, modo="SECCION", seccion_id=escuela.s3b.id)
    assert otra["resultado"] == "otra_seccion" and "5.º C" in otra["mensaje"]
    assert Registro.objects.count() == 2


def test_auxiliar_escanea_cualquier_seccion_en_modo_puerta(escuela):
    res = escanear(cliente_de(escuela.auxiliar), escuela.ajeno.carnet.contenido_qr, modo="PUERTA")
    assert res["resultado"] == "ok" and res["seccion"]["nombre_corto"] == "5.º C"


def test_carnet_regenerado_invalida_el_anterior(escuela):
    anterior = escuela.mateo.carnet.contenido_qr
    nuevo = Carnet.emitir(escuela.mateo.estudiante)
    c = cliente_de(escuela.auxiliar)
    assert escanear(c, anterior)["resultado"] == "invalido"
    assert escanear(c, nuevo.contenido_qr)["resultado"] == "ok"


def test_qr_no_contiene_datos_personales(escuela):
    contenido = escuela.mateo.carnet.contenido_qr
    assert contenido.startswith("AE1.") and len(contenido) == 4 + 22
    assert "Flores" not in contenido and "Mateo" not in contenido and escuela.mateo.estudiante.codigo_estudiante not in contenido


# ---------------------------------------------------------------- justificar y cierre
def test_justificar_falta(escuela):
    c = cliente_de(escuela.marisol)
    rid = enviar(c, marca(escuela, escuela.mateo, "F"))[0]["registro_id"]
    r = c.post(f"/api/v1/registros/{rid}/justificar/", {"motivo": "SALUD", "detalle": "Cita médica"})
    assert r.status_code == 200, r.content
    assert r.json()["estado"] == "J" and r.json()["estado_original"] == "F"
    assert Justificacion.objects.get().motivo == "SALUD"


def test_justificar_registro_ajeno_da_404(escuela):
    otro = cliente_de(escuela.otro)
    rid = enviar(otro, marca(escuela, escuela.ajeno, "F", seccion=escuela.s5c))[0]["registro_id"]
    assert cliente_de(escuela.marisol).post(f"/api/v1/registros/{rid}/justificar/", {"motivo": "SALUD"}).status_code == 404


def test_cerrar_dia_marca_falta_a_los_sin_registrar(escuela):
    enviar(cliente_de(escuela.marisol), marca(escuela, escuela.mateo, "P"))
    resumen = cerrar_dia(date(2026, 10, 6))
    assert resumen["faltas_creadas"] == 1
    assert Registro.objects.get(matricula=escuela.luciana.matricula).estado == "F"
    assert SesionAsistencia.objects.get().estado == "CERRADA"
    assert cerrar_dia(date(2026, 10, 8))["omitido"]


# ---------------------------------------------------------------- nómina e historial
def test_nomina_con_etag(escuela):
    c = cliente_de(escuela.marisol)
    r = c.get("/api/v1/movil/nomina/")
    assert r.status_code == 200
    seccion = r.json()["secciones"][0]
    assert seccion["estudiantes"][0]["apellido_paterno"] == "Apaza"
    assert seccion["estudiantes"][0]["carnet_hash"] == escuela.luciana.carnet.token_hash
    assert c.get("/api/v1/movil/nomina/", HTTP_IF_NONE_MATCH=r["ETag"]).status_code == 304


def test_historial_del_mes(escuela):
    c = cliente_de(escuela.marisol)
    enviar(c, marca(escuela, escuela.mateo, "T"))
    data = c.get(f"/api/v1/estudiantes/{escuela.mateo.estudiante.id}/historial/?mes=2026-10").json()
    assert data["mes_texto"] == "Octubre 2026"
    assert data["indicadores"]["tardanzas"] == 1 and data["indicadores"]["porcentaje_texto"] == "100 %"
    dia8 = next(d for d in data["dias"] if d["dia"] == 8)
    assert dia8["habil"] is False
    assert data["apoderado"]["celular"] == "987654321" and data["puede_llamar"] is True
