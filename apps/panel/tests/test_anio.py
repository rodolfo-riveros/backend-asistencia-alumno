"""Año escolar nuevo, paso de año por salón, menú agrupado e inicio con primeros pasos."""

from datetime import date

import pytest
from django.test import Client

from apps.academico.models import Asignacion, Curso, Grado, Seccion
from apps.estudiantes.models import Estudiante, Matricula
from apps.estudiantes.promocion import NO_MATRICULAR, aplicar, seccion_sugerida
from apps.institucion.models import AnioEscolar, DiaNoLectivo
from apps.panel.mixins import MENU
from conftest import crear_usuario

pytestmark = pytest.mark.django_db


def cliente(usuario):
    c = Client()
    c.force_login(usuario)
    return c


@pytest.fixture
def admin(escuela):
    return crear_usuario("admin@demo.edu.pe", "ADMIN", "Ana", "Admin")


@pytest.fixture
def con_cuarto(escuela):
    """Agrega 4.º grado para poder pasar a los de 3.º B."""
    g4 = Grado.objects.create(nivel=escuela.s3b.grado.nivel, numero=4, nombre="4.º grado", orden=4)
    return g4


def crear_2027(c, **extra):
    datos = {
        "accion": "crear", "anio": 2027, "fecha_inicio": "2027-03-15", "fecha_fin": "2027-12-17",
        "copiar_de": AnioEscolar.objects.get(anio=2026).pk, "copiar": "todo", "cuando": "despues", **extra,
    }
    return c.post("/panel/anio/", datos)


def test_crear_anio_copiando_secciones_cursos_y_feriados(admin, escuela):
    Asignacion.objects.create(seccion=escuela.s3b, curso=Curso.objects.create(nombre="Arte"), docente=escuela.marisol)
    r = crear_2027(cliente(admin))
    nuevo = AnioEscolar.objects.get(anio=2027)
    assert r.status_code == 302 and "/panel/anio/promocion/" in r["Location"]
    assert not nuevo.activo and AnioEscolar.activo_actual().anio == 2026  # no se activa solo
    copia = Seccion.objects.get(anio_escolar=nuevo, grado=escuela.s3b.grado, letra="B")
    assert copia.tutor == escuela.marisol and copia.turno == escuela.s3b.turno
    assert Asignacion.objects.filter(seccion=copia, docente=escuela.marisol).exists()
    assert DiaNoLectivo.objects.filter(anio_escolar=nuevo, fecha=date(2027, 7, 28)).exists()


def test_activar_anio_explicitamente(admin, escuela):
    c = cliente(admin)
    crear_2027(c)
    nuevo = AnioEscolar.objects.get(anio=2027)
    c.post("/panel/anio/", {"accion": "activar", "anio_id": nuevo.pk})
    assert AnioEscolar.activo_actual() == nuevo
    # Editar las fechas no desactiva el año
    c.post("/panel/anio/", {"accion": "editar", "anio_id": nuevo.pk, f"a{nuevo.pk}-fecha_inicio": "2027-03-08", f"a{nuevo.pk}-fecha_fin": "2027-12-17"})
    nuevo.refresh_from_db()
    assert nuevo.activo and nuevo.fecha_inicio == date(2027, 3, 8)


def test_pasar_un_salon_completo_con_repitente_y_retiro(admin, escuela, con_cuarto):
    c = cliente(admin)
    crear_2027(c)
    nuevo = AnioEscolar.objects.get(anio=2027)
    cuarto_b = Seccion.objects.create(anio_escolar=nuevo, grado=con_cuarto, letra="B", turno=escuela.turno)
    tercero_b_2027 = Seccion.objects.get(anio_escolar=nuevo, grado=escuela.s3b.grado, letra="B")
    assert seccion_sugerida(escuela.s3b, nuevo) == cuarto_b

    # La pantalla del salón muestra a todos con el destino sugerido
    html = c.get(f"/panel/anio/promocion/{escuela.s3b.pk}/?destino={nuevo.pk}").content.decode()
    assert "Flores Cusi" in html and "Todos pasan a" in html

    # Mateo repite (3.º B 2027) y Luciana no continúa
    r = c.post(f"/panel/anio/promocion/{escuela.s3b.pk}/?destino={nuevo.pk}", {
        f"m_{escuela.mateo.matricula.pk}": str(tercero_b_2027.pk),
        f"m_{escuela.luciana.matricula.pk}": NO_MATRICULAR,
    }, follow=True)
    assert "1 repiten" in r.content.decode() and "1 no se matriculan" in r.content.decode()
    assert Matricula.objects.get(estudiante=escuela.mateo.estudiante, anio_escolar=nuevo).seccion == tercero_b_2027
    assert not Matricula.objects.filter(estudiante=escuela.luciana.estudiante, anio_escolar=nuevo).exists()
    # La matrícula de 2026 no se toca
    assert Matricula.objects.get(pk=escuela.mateo.matricula.pk).anio_escolar.anio == 2026


def test_pasar_a_todos_respeta_lo_ya_ajustado_y_no_duplica(admin, escuela, con_cuarto):
    c = cliente(admin)
    crear_2027(c)
    nuevo = AnioEscolar.objects.get(anio=2027)
    cuarto_b = Seccion.objects.create(anio_escolar=nuevo, grado=con_cuarto, letra="B", turno=escuela.turno)
    tercero_b_2027 = Seccion.objects.get(anio_escolar=nuevo, grado=escuela.s3b.grado, letra="B")
    aplicar(escuela.s3b, nuevo, {escuela.mateo.matricula.pk: str(tercero_b_2027.pk)})  # repite

    origen = AnioEscolar.objects.get(anio=2026)
    c.post("/panel/anio/promocion/", {"origen": origen.pk, "destino": nuevo.pk})
    c.post("/panel/anio/promocion/", {"origen": origen.pk, "destino": nuevo.pk})  # dos veces: idempotente
    assert Matricula.objects.get(estudiante=escuela.mateo.estudiante, anio_escolar=nuevo).seccion == tercero_b_2027
    assert Matricula.objects.get(estudiante=escuela.luciana.estudiante, anio_escolar=nuevo).seccion == cuarto_b
    assert Matricula.objects.filter(anio_escolar=nuevo).count() == 2  # 5.º C egresa (no hay 6.º)


def test_ultimo_grado_egresa_por_defecto(admin, escuela):
    nuevo = AnioEscolar.objects.create(anio=2027, fecha_inicio=date(2027, 3, 15), fecha_fin=date(2027, 12, 17))
    r = aplicar(escuela.s5c, nuevo, {})
    assert r["no_matriculados"] == 1 and not Matricula.objects.filter(anio_escolar=nuevo).exists()
    html = cliente(admin).get(f"/panel/anio/promocion/?origen={escuela.anio.pk}&destino={nuevo.pk}").content.decode()
    assert "Egresan" in html


def test_menu_agrupado_en_orden_de_trabajo(admin):
    claves = [m[0] for m in MENU]
    assert claves.index("anio") < claves.index("secciones") < claves.index("docentes") < claves.index("estudiantes")
    assert claves[0] == "dashboard" and claves.index("estudiantes") < claves.index("reportes")
    html = cliente(admin).get("/panel/").content.decode()
    for grupo in ("Organización del año", "Personas", "Asistencia", "Sistema"):
        assert grupo in html
    assert "Año escolar <strong>2026</strong>" in html


def test_secciones_de_un_anio_no_activo_y_crear_por_grado(admin, escuela):
    nuevo = AnioEscolar.objects.create(anio=2027, fecha_inicio=date(2027, 3, 15), fecha_fin=date(2027, 12, 17))
    c = cliente(admin)
    html = c.get(f"/panel/secciones/?anio={nuevo.pk}").content.decode()
    assert "aún no es el año activo" in html and "3.º grado" in html
    form = c.get(f"/panel/secciones/nueva/?anio={nuevo.pk}&grado={escuela.s3b.grado.pk}").content.decode()
    assert 'value="A"' in form  # sugiere la primera letra libre
    c.post(f"/panel/secciones/nueva/?anio={nuevo.pk}", {
        "anio": nuevo.pk, "grado": escuela.s3b.grado.pk, "letra": "A", "turno": escuela.turno.pk, "capacidad": 30,
    })
    assert Seccion.objects.filter(anio_escolar=nuevo, grado=escuela.s3b.grado, letra="A").exists()


def test_estudiante_sin_matricula_previa_no_aparece_en_promocion(admin, escuela):
    suelto = Estudiante.objects.create(codigo_estudiante="X1", apellido_paterno="Sin", nombres="Matrícula")
    nuevo = AnioEscolar.objects.create(anio=2027, fecha_inicio=date(2027, 3, 15), fecha_fin=date(2027, 12, 17))
    html = cliente(admin).get(f"/panel/anio/promocion/{escuela.s3b.pk}/?destino={nuevo.pk}").content.decode()
    assert suelto.apellido_paterno not in html
