"""Fixtures compartidas: una escuela mínima y un reloj controlable."""

from datetime import date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.academico.models import Grado, Nivel, Seccion
from apps.cuentas.models import Usuario
from apps.estudiantes.models import Apoderado, Carnet, Estudiante, Matricula
from apps.institucion.models import AnioEscolar, DiaNoLectivo, Turno

LIMA = ZoneInfo("America/Lima")


def lima(y, m, d, h=0, mi=0, s=0):
    return datetime(y, m, d, h, mi, s, tzinfo=LIMA)


@pytest.fixture
def reloj(monkeypatch):
    """reloj.poner(lima(2026, 10, 6, 7, 50)) fija la hora del servidor."""
    from django.utils import timezone

    estado = {"ahora": lima(2026, 10, 6, 7, 50)}  # martes 6 de octubre

    def ahora():
        return estado["ahora"]

    monkeypatch.setattr(timezone, "now", ahora)
    return SimpleNamespace(poner=lambda dt: estado.update(ahora=dt), ahora=ahora)


def crear_usuario(email, rol, nombres="Usuario", apellidos="Prueba"):
    return Usuario.objects.create_user(email=email, password="clave-segura-123", rol_id=rol, nombres=nombres, apellidos=apellidos)


def cliente_de(usuario):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(usuario).access_token}")
    return c


@pytest.fixture
def escuela(db, reloj):
    anio = AnioEscolar.objects.create(anio=2026, fecha_inicio=date(2026, 3, 16), fecha_fin=date(2026, 12, 18), activo=True)
    DiaNoLectivo.objects.create(anio_escolar=anio, fecha=date(2026, 10, 8), descripcion="Combate de Angamos")
    manana = Turno.objects.create(nombre="MANANA", hora_ingreso=time(7, 45), tolerancia_min=10)
    primaria = Nivel.objects.create(nombre="PRIMARIA")
    g3 = Grado.objects.create(nivel=primaria, numero=3, nombre="3.º grado", orden=3)
    g5 = Grado.objects.create(nivel=primaria, numero=5, nombre="5.º grado", orden=5)

    marisol = crear_usuario("m.quispe@ie-ejemplo.edu.pe", "DOCENTE", "Marisol", "Quispe")
    otro = crear_usuario("otro@ie-ejemplo.edu.pe", "DOCENTE", "Edwin", "Mamani")
    director = crear_usuario("director@demo.edu.pe", "DIRECTOR", "Carlos", "Paucar")
    auxiliar = crear_usuario("auxiliar@demo.edu.pe", "AUXILIAR", "Nancy", "Choque")

    s3b = Seccion.objects.create(anio_escolar=anio, grado=g3, letra="B", turno=manana, tutor=marisol)
    s5c = Seccion.objects.create(anio_escolar=anio, grado=g5, letra="C", turno=manana, tutor=otro)

    def alumno(seccion, ap, am, nom, codigo):
        e = Estudiante.objects.create(codigo_estudiante=codigo, dni=None, apellido_paterno=ap, apellido_materno=am, nombres=nom)
        Apoderado.objects.create(estudiante=e, nombre=f"Madre de {nom}", parentesco="Madre", celular="987654321")
        m = Matricula.objects.create(estudiante=e, seccion=seccion, anio_escolar=anio, fecha_alta=anio.fecha_inicio)
        return SimpleNamespace(estudiante=e, matricula=m, carnet=Carnet.emitir(e))

    mateo = alumno(s3b, "Flores", "Cusi", "Mateo Joaquín", "A001")
    luciana = alumno(s3b, "Apaza", "Huamán", "Luciana Valeria", "A002")
    ajeno = alumno(s5c, "Rojas", "Ccori", "Fabián", "A003")

    return SimpleNamespace(
        anio=anio, turno=manana, s3b=s3b, s5c=s5c, marisol=marisol, otro=otro, director=director,
        auxiliar=auxiliar, mateo=mateo, luciana=luciana, ajeno=ajeno, reloj=reloj,
    )
