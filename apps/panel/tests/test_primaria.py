"""Primaria: el tutor dicta todos los cursos y los docentes entran con su DNI."""

import pytest
from django.test import Client

from apps.academico.models import Asignacion, BloqueHorario, Curso
from apps.cuentas.models import Usuario
from conftest import crear_usuario

pytestmark = pytest.mark.django_db


def cliente(usuario):
    c = Client()
    c.force_login(usuario)
    return c


@pytest.fixture
def cursos(escuela):
    return [Curso.objects.create(nombre=n) for n in ("Matemática", "Comunicación", "Inglés")]


def profe_ingles():
    return Usuario.objects.create_user("ingles@ie.edu.pe", "x", nombres="Ana", apellidos="Inglés", rol_id="DOCENTE")


# ------------------------------------------------------------------ DNI como contraseña
def nuevo_docente(c, **extra):
    datos = {"nombres": "Rosa", "apellidos": "Huamán", "dni": "45678912", "email": "rosa@ie.edu.pe", "is_active": "on", **extra}
    return c.post("/panel/docentes/", datos, follow=True)


def test_docente_entra_a_la_app_con_correo_y_dni(escuela):
    nuevo_docente(cliente(escuela.director))
    r = Client().post("/api/v1/auth/login/", {"email": "rosa@ie.edu.pe", "password": "45678912"}, content_type="application/json")
    assert r.status_code == 200 and "access" in r.json()


@pytest.mark.parametrize("dni, error", [("", "Ingresa su DNI"), ("1234", "8 dígitos"), ("4567891A", "8 dígitos")])
def test_dni_obligatorio_y_valido(escuela, dni, error):
    r = nuevo_docente(cliente(escuela.director), dni=dni)
    assert error in r.content.decode() and not Usuario.objects.filter(email="rosa@ie.edu.pe").exists()


def test_dni_no_se_repite(escuela):
    c = cliente(escuela.director)
    nuevo_docente(c)
    r = nuevo_docente(c, email="otra@ie.edu.pe")
    assert "Ya existe un usuario con este DNI" in r.content.decode()


def test_restablecer_vuelve_al_dni_y_desbloquea(escuela):
    c = cliente(escuela.director)
    nuevo_docente(c)
    d = Usuario.objects.get(email="rosa@ie.edu.pe")
    d.set_password("otra-clave-que-olvido")
    d.intentos_fallidos = 9
    d.save()
    c.post(f"/panel/docentes/{d.pk}/", {"accion": "restablecer"})
    d.refresh_from_db()
    assert d.check_password("45678912") and d.intentos_fallidos == 0 and not d.debe_cambiar_password


def test_corregir_dni_mueve_la_clave(escuela):
    c = cliente(escuela.director)
    nuevo_docente(c)
    d = Usuario.objects.get(email="rosa@ie.edu.pe")
    c.post(f"/panel/docentes/{d.pk}/", {"accion": "datos", "nombres": "Rosa", "apellidos": "Huamán", "dni": "45678913",
                                        "email": "rosa@ie.edu.pe", "rol": "DOCENTE", "is_active": "on"})
    d.refresh_from_db()
    assert d.dni == "45678913" and d.check_password("45678913")


def test_usuario_sin_dni_recibe_clave_temporal(escuela):
    admin = crear_usuario("admin@demo.edu.pe", "ADMIN", "Ana", "Admin")
    r = cliente(admin).post("/panel/usuarios/nuevo/", {
        "nombres": "Sec", "apellidos": "Retaria", "email": "sec@ie.edu.pe", "rol": "DOCENTE", "is_active": "on",
    }, follow=True)
    assert "Contraseña temporal" in r.content.decode()
    assert Usuario.objects.get(email="sec@ie.edu.pe").debe_cambiar_password


# ------------------------------------------------------------------ el tutor dicta todo
def test_seccion_nueva_con_tutor_le_asigna_todos_los_cursos(escuela, cursos):
    cliente(escuela.director).post("/panel/secciones/nueva/", {
        "grado": escuela.s3b.grado.pk, "letra": "D", "turno": escuela.turno.pk, "capacidad": 30,
        "tutor": escuela.otro.pk, "tutor_dicta_todo": "on",
    })
    asig = Asignacion.objects.filter(seccion__letra="D")
    assert asig.count() == 3 and set(asig.values_list("docente_id", flat=True)) == {escuela.otro.pk}


def test_cambiar_tutor_pasa_sus_cursos_y_respeta_los_de_otros(escuela, cursos):
    mat, com, ingles = cursos
    ana = profe_ingles()
    Asignacion.objects.create(seccion=escuela.s3b, curso=mat, docente=escuela.marisol)
    Asignacion.objects.create(seccion=escuela.s3b, curso=ingles, docente=ana)
    cliente(escuela.director).post(f"/panel/docentes/{escuela.otro.pk}/", {"accion": "tutoria", "seccion": escuela.s3b.pk, "todos_cursos": "on"})
    por_curso = dict(Asignacion.objects.filter(seccion=escuela.s3b).values_list("curso__nombre", "docente_id"))
    assert por_curso == {"Matemática": escuela.otro.pk, "Comunicación": escuela.otro.pk, "Inglés": ana.pk}


def test_horario_sin_asignar_antes_usa_al_tutor_en_varios_dias(escuela, cursos):
    r = cliente(escuela.director).post(f"/panel/horarios/{escuela.s3b.pk}/", {
        "curso": cursos[0].pk, "dias": [1, 3, 5], "hora_inicio": "08:00", "hora_fin": "08:45",
    }, follow=True)
    assert "agregado en 3 días" in r.content.decode()
    assert BloqueHorario.objects.filter(seccion=escuela.s3b, asignacion__docente=escuela.marisol).count() == 3


def test_horario_con_otro_docente_y_sin_choques_en_el_salon(escuela, cursos):
    mat, _, ingles = cursos
    ana = profe_ingles()
    c = cliente(escuela.director)
    c.post(f"/panel/horarios/{escuela.s3b.pk}/", {"curso": ingles.pk, "docente": ana.pk, "dias": [2], "hora_inicio": "10:00", "hora_fin": "10:45"})
    assert Asignacion.objects.get(seccion=escuela.s3b, curso=ingles).docente == ana
    # Mismo salón y misma hora: se rechaza todo, ningún día queda a medias
    r = c.post(f"/panel/horarios/{escuela.s3b.pk}/", {"curso": mat.pk, "dias": [1, 2], "hora_inicio": "10:15", "hora_fin": "11:00"})
    assert "ocupado" in r.content.decode()
    assert BloqueHorario.objects.filter(seccion=escuela.s3b).count() == 1
    assert not Asignacion.objects.filter(seccion=escuela.s3b, curso=mat).exists()


def test_seccion_sin_tutor_pide_docente(escuela, cursos):
    escuela.s3b.tutor = None
    escuela.s3b.save()
    r = cliente(escuela.director).post(f"/panel/horarios/{escuela.s3b.pk}/", {"curso": cursos[0].pk, "dias": [1], "hora_inicio": "08:00", "hora_fin": "08:45"})
    assert "no tiene tutor" in r.content.decode() and not BloqueHorario.objects.exists()
