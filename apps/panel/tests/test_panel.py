import io
from datetime import time

import pytest
from django.test import Client
from openpyxl import Workbook, load_workbook

from apps.academico.models import Asignacion, BloqueHorario, Curso
from apps.cuentas.models import Usuario
from apps.estudiantes.models import Carnet, Estudiante, Matricula
from apps.institucion.models import DiaNoLectivo
from conftest import crear_usuario

pytestmark = pytest.mark.django_db


def cliente(usuario):
    c = Client()
    c.force_login(usuario)
    return c


# ------------------------------------------------------------------ acceso
def test_docente_no_entra_al_panel(escuela):
    r = Client().post("/panel/login/", {"email": escuela.marisol.email, "password": "clave-segura-123"})
    assert "no tiene acceso al panel" in r.content.decode()
    assert cliente(escuela.marisol).get("/panel/estudiantes/").status_code == 403


def test_sin_sesion_redirige_al_login():
    r = Client().get("/panel/estudiantes/")
    assert r.status_code == 302 and r["Location"].startswith("/panel/login/")


def test_director_entra_y_ve_todas_las_paginas(escuela):
    r = Client().post("/panel/login/", {"email": escuela.director.email, "password": "clave-segura-123"})
    assert r.status_code == 302 and r["Location"] == "/panel/"
    c = cliente(escuela.director)
    est = escuela.mateo.estudiante
    for url in [
        "/panel/", "/panel/anio/", "/panel/reportes/", "/panel/estudiantes/", "/panel/estudiantes/nuevo/", f"/panel/estudiantes/{est.pk}/",
        "/panel/secciones/", "/panel/secciones/nueva/", f"/panel/secciones/{escuela.s3b.pk}/",
        "/panel/docentes/", "/panel/docentes/nuevo/", f"/panel/docentes/{escuela.marisol.pk}/",
        "/panel/cursos/", f"/panel/horarios/{escuela.s3b.pk}/", "/panel/carnets/",
        f"/panel/carnets/seccion/{escuela.s3b.pk}/", f"/panel/carnets/estudiante/{est.pk}/",
        "/panel/importar/", "/panel/configuracion/calendario/",
    ]:
        assert c.get(url).status_code == 200, url
    # Configuración y usuarios son del administrador (rol DIRECTOR no tiene esos permisos).
    assert c.get("/panel/configuracion/").status_code == 403


def test_usuarios_solo_admin(escuela):
    assert cliente(escuela.director).get("/panel/usuarios/").status_code == 403
    admin = crear_usuario("admin@demo.edu.pe", "ADMIN")
    c = cliente(admin)
    for url in ("/panel/usuarios/", "/panel/usuarios/nuevo/", "/panel/usuarios/roles/", "/panel/usuarios/roles/nuevo/",
                f"/panel/usuarios/{escuela.marisol.pk}/", "/panel/configuracion/", "/panel/secciones/grados/"):
        assert c.get(url).status_code == 200, url


def test_director_no_cambia_configuracion(escuela):
    r = cliente(escuela.director).post("/panel/configuracion/", {"accion": "reglas", "umbral_faltas": 9})
    assert r.status_code == 403


def test_clave_temporal_obliga_a_cambiarla(escuela):
    escuela.director.debe_cambiar_password = True
    escuela.director.save()
    c = cliente(escuela.director)
    assert c.get("/panel/estudiantes/")["Location"] == "/panel/cambiar-contrasena/"
    r = c.post("/panel/cambiar-contrasena/", {"nueva": "Otra-clave-2026", "repetir": "Otra-clave-2026"})
    assert r.status_code == 302
    escuela.director.refresh_from_db()
    assert not escuela.director.debe_cambiar_password


# ------------------------------------------------------------------ CRUD
def test_crear_docente_con_dni_como_clave(escuela):
    r = cliente(escuela.director).post(
        "/panel/docentes/", {"nombres": "Rosa", "apellidos": "Huamán", "dni": "45678912", "email": "R.Huaman@IE.edu.pe", "is_active": "on"},
        follow=True,
    )
    assert "su DNI como contraseña" in r.content.decode()
    d = Usuario.objects.get(email="r.huaman@ie.edu.pe")
    assert d.rol_id == "DOCENTE" and not d.debe_cambiar_password and d.check_password("45678912")


def test_asignar_tutoria_y_curso(escuela):
    curso = Curso.objects.create(nombre="Inglés")
    c = cliente(escuela.director)
    c.post(f"/panel/docentes/{escuela.otro.pk}/", {"accion": "asignar", "seccion": escuela.s3b.pk, "curso": curso.pk})
    assert Asignacion.objects.filter(docente=escuela.otro, seccion=escuela.s3b, curso=curso).exists()
    c.post(f"/panel/docentes/{escuela.otro.pk}/", {"accion": "tutoria", "seccion": escuela.s3b.pk})
    escuela.s3b.refresh_from_db()
    assert escuela.s3b.tutor == escuela.otro


def test_seccion_duplicada_se_rechaza(escuela):
    r = cliente(escuela.director).post("/panel/secciones/nueva/", {
        "grado": escuela.s3b.grado.pk, "letra": "b", "turno": escuela.turno.pk, "capacidad": 30,
    })
    assert "Ya existe" in r.content.decode()


def test_horario_detecta_choque_de_docente(escuela):
    curso = Curso.objects.create(nombre="Arte")
    a1 = Asignacion.objects.create(seccion=escuela.s3b, curso=curso, docente=escuela.otro)
    a2 = Asignacion.objects.create(seccion=escuela.s5c, curso=curso, docente=escuela.otro)
    BloqueHorario.objects.create(seccion=escuela.s3b, asignacion=a1, dia_semana=1, hora_inicio=time(8), hora_fin=time(8, 45))
    r = cliente(escuela.director).post(f"/panel/horarios/{escuela.s5c.pk}/", {
        "curso": curso.pk, "dias": [1], "hora_inicio": "08:30", "hora_fin": "09:15",
    })
    assert "Choque de horario" in r.content.decode()
    assert BloqueHorario.objects.count() == 1


def test_calendario_agrega_rango_sin_fines_de_semana(escuela):
    cliente(escuela.director).post("/panel/configuracion/calendario/", {
        "desde": "2026-07-27", "hasta": "2026-08-09", "motivo": "VACACIONES", "descripcion": "Medio año",
    })
    assert DiaNoLectivo.objects.filter(motivo="VACACIONES").count() == 10


# ------------------------------------------------------------------ estudiantes y carnets
def test_regenerar_carnet_desde_la_ficha(escuela):
    est = escuela.mateo.estudiante
    anterior = escuela.mateo.carnet
    cliente(escuela.director).post(f"/panel/estudiantes/{est.pk}/", {"accion": "regenerar_carnet"})
    anterior.refresh_from_db()
    assert anterior.estado == "REVOCADO"
    assert Carnet.objects.filter(estudiante=est, estado="ACTIVO").count() == 1


def test_baja_de_matricula_da_de_baja_el_carnet(escuela):
    est = escuela.mateo.estudiante
    cliente(escuela.director).post(f"/panel/estudiantes/{est.pk}/", {
        "accion": "baja_matricula", "estado": "TRASLADADO", "fecha_baja": "2026-10-06",
    })
    assert Matricula.objects.get(estudiante=est).estado == "TRASLADADO"
    assert not Carnet.objects.filter(estudiante=est, estado="ACTIVO").exists()


def test_hoja_de_carnets_con_qr_real(escuela):
    html = cliente(escuela.director).get(f"/panel/carnets/seccion/{escuela.s3b.pk}/").content.decode()
    assert html.count('class="carnet"') == 2 and "<svg" in html
    assert "hoja 1 de 1" in html and "sin DNI ni datos personales" in html


def test_busqueda_htmx_devuelve_solo_la_tabla(escuela):
    r = cliente(escuela.director).get("/panel/estudiantes/?q=flores", HTTP_HX_REQUEST="true")
    html = r.content.decode()
    assert "Flores" in html and "Apaza" not in html and "<aside" not in html


# ------------------------------------------------------------------ importación
def excel(filas, encabezado=None):
    libro = Workbook()
    hoja = libro.active
    hoja.append(encabezado or [
        "codigo_estudiante", "dni", "apellido_paterno", "apellido_materno", "nombres", "sexo", "fecha_nacimiento",
        "grado", "seccion", "apoderado_nombre", "apoderado_parentesco", "apoderado_celular",
    ])
    for f in filas:
        hoja.append(f)
    salida = io.BytesIO()
    libro.save(salida)
    salida.seek(0)
    salida.name = "nomina.xlsx"
    return salida


def test_importar_30_alumnos_con_2_filas_erroneas(escuela):
    filas = [
        [f"B{i:04d}", f"7{i:07d}", "Quispe", "Mamani", f"Alumno {i}", "M", "14/05/2018", "3", "B", "Rosa Mamani", "Madre", "987654321"]
        for i in range(1, 29)
    ]
    filas.append(["B0029", "123", "Rojas", "", "Error DNI", "F", "", "3", "B", "", "", ""])  # DNI inválido
    filas.append(["B0030", "", "Torres", "", "Error sección", "F", "", "3", "Z", "", "", ""])  # sección inexistente
    c = cliente(escuela.director)

    r = c.post("/panel/importar/", {"archivo": excel(filas)})
    html = r.content.decode()
    assert "DNI inválido" in html and "No existe la sección" in html
    assert Estudiante.objects.filter(codigo_estudiante__startswith="B").count() == 0  # nada guardado aún

    token = c.session["importacion_estudiantes"]["token"]
    r = c.post("/panel/importar/", {"accion": "confirmar", "token": token}, follow=True)
    assert "28 estudiantes nuevos" in r.content.decode()
    nuevos = Estudiante.objects.filter(codigo_estudiante__startswith="B")
    assert nuevos.count() == 28
    assert not nuevos.filter(codigo_estudiante__in=["B0029", "B0030"]).exists()
    assert Matricula.objects.filter(estudiante__in=nuevos, seccion=escuela.s3b).count() == 28
    assert Carnet.objects.filter(estudiante__in=nuevos, estado="ACTIVO").count() == 28
    assert nuevos.first().apoderados.get().celular == "987654321"


def test_importar_reconoce_encabezados_de_siagie_y_actualiza(escuela):
    encabezado = ["Código del Estudiante", "DNI", "Apellido Paterno", "Apellido Materno", "Nombres", "Sexo",
                  "Fecha de Nacimiento", "Grado", "Sección"]
    filas = [
        ["A001", "", "FLORES", "CUSI", "MATEO JOAQUÍN", "Hombre", "2018-05-14", "TERCERO", "B"],  # ya existe
        ["S0001", "", "PUMA", "SULLCA", "THIAGO", "H", "", "3.º", "B"],
    ]
    c = cliente(escuela.director)
    r = c.post("/panel/importar/", {"archivo": excel(filas, encabezado)})
    html = r.content.decode()
    assert "Actualizar" in html and "Nuevo" in html
    c.post("/panel/importar/", {"accion": "confirmar", "token": c.session["importacion_estudiantes"]["token"]})
    assert Estudiante.objects.get(codigo_estudiante="S0001").nombres == "Thiago"
    assert Estudiante.objects.get(codigo_estudiante="A001").sexo == "M"


def test_archivo_sin_columnas_obligatorias(escuela):
    r = cliente(escuela.director).post("/panel/importar/", {"archivo": excel([["x"]], ["columna_rara"])})
    assert "No se encontraron las columnas obligatorias" in r.content.decode()


def test_plantilla_descargable(escuela):
    r = cliente(escuela.director).get("/panel/importar/plantilla.xlsx")
    libro = load_workbook(io.BytesIO(r.content))
    assert [c.value for c in libro["Estudiantes"][1]][:3] == ["codigo_estudiante", "dni", "apellido_paterno"]
