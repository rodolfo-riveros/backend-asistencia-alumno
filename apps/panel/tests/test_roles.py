"""Roles y permisos configurables, niveles/grados e institución dinámicos."""

import io
import uuid

import pytest
from django.test import Client
from PIL import Image
from rest_framework.test import APIClient

from apps.academico.models import Grado, Nivel
from apps.cuentas.models import Rol, Usuario
from apps.institucion.models import Institucion
from conftest import cliente_de, crear_usuario, lima

pytestmark = pytest.mark.django_db


def cliente(usuario):
    c = Client()
    c.force_login(usuario)
    return c


@pytest.fixture
def admin(escuela):
    return crear_usuario("admin@demo.edu.pe", "ADMIN", "Ana", "Admin")


def test_roles_iniciales_y_permisos_por_defecto(escuela):
    assert set(Rol.objects.values_list("codigo", flat=True)) >= {"ADMIN", "DIRECTOR", "DOCENTE", "AUXILIAR"}
    assert escuela.marisol.puede("asistencia.pasar_lista") and not escuela.marisol.acceso_panel
    assert escuela.auxiliar.puede("asistencia.escanear_puerta") and not escuela.auxiliar.puede("asistencia.pasar_lista")
    assert escuela.director.puede("panel.reportes") and not escuela.director.puede("panel.usuarios")


def test_crear_rol_y_usuario_desde_el_panel(admin, escuela):
    c = cliente(admin)
    r = c.post("/panel/usuarios/roles/nuevo/", {
        "nombre": "Secretaría", "descripcion": "Atiende matrículas", "permisos": ["panel.estudiantes", "panel.carnets"],
    })
    assert r.status_code == 302
    rol = Rol.objects.get(nombre="Secretaría")
    assert rol.codigo == "SECRETARIA" and rol.permisos == ["panel.estudiantes", "panel.carnets"]

    r = c.post("/panel/usuarios/nuevo/", {
        "nombres": "Lucía", "apellidos": "Ramos", "email": "secretaria@ie.edu.pe", "rol": rol.codigo, "is_active": "on",
    }, follow=True)
    assert "Contraseña temporal" in r.content.decode()
    u = Usuario.objects.get(email="secretaria@ie.edu.pe")
    assert u.rol == rol and u.debe_cambiar_password

    # Entra al panel y solo ve lo que su rol permite
    u.debe_cambiar_password = False
    u.save()
    s = cliente(u)
    html = s.get("/panel/estudiantes/").content.decode()
    assert "Carnets QR" in html and "Reportes" not in html and "Dashboard del día" not in html
    assert s.get("/panel/reportes/").status_code == 403
    assert s.get("/panel/").status_code == 403

    # Al dar un permiso al rol, se aplica de inmediato
    c.post(f"/panel/usuarios/roles/{rol.pk}/", {"nombre": "Secretaría", "permisos": ["panel.estudiantes", "panel.reportes"]})
    assert cliente(Usuario.objects.get(pk=u.pk)).get("/panel/reportes/").status_code == 200


def test_login_del_panel_lleva_a_la_primera_seccion_permitida(admin):
    rol = Rol.objects.create(codigo="IMPORTADOR", nombre="Importador", permisos=["panel.importar"])
    crear_usuario("imp@ie.edu.pe", "IMPORTADOR")
    r = Client().post("/panel/login/", {"email": "imp@ie.edu.pe", "password": "clave-segura-123"})
    assert r.status_code == 302 and r["Location"] == "/panel/importar/"
    assert rol.usuarios.count() == 1


def test_app_requiere_permiso_de_acceso(escuela):
    Rol.objects.create(codigo="SOLO_PANEL", nombre="Solo panel", permisos=["panel.reportes"])
    crear_usuario("panel@ie.edu.pe", "SOLO_PANEL")
    r = APIClient().post("/api/v1/auth/login/", {"email": "panel@ie.edu.pe", "password": "clave-segura-123"}, format="json")
    assert r.status_code == 403 and r.json()["codigo"] == "sin_acceso_app"
    ok = APIClient().post("/api/v1/auth/login/", {"email": escuela.marisol.email, "password": "clave-segura-123"}, format="json")
    assert "asistencia.pasar_lista" in ok.json()["usuario"]["permisos"]


def test_rol_personalizado_con_todas_las_secciones_marca_en_cualquier_seccion(escuela):
    Rol.objects.create(
        codigo="COORDINADOR", nombre="Coordinador",
        permisos=["app.acceso", "asistencia.todas_las_secciones", "asistencia.justificar", "estudiantes.ver_historial"],
    )
    coord = crear_usuario("coord@ie.edu.pe", "COORDINADOR")
    c = cliente_de(coord)
    hoy = c.get("/api/v1/movil/hoy/").json()
    assert {t["seccion_id"] for t in hoy["tarjetas"]} == {escuela.s3b.id, escuela.s5c.id}
    r = c.post("/api/v1/asistencia/lote/", {"marcas": [{
        "uuid_cliente": str(uuid.uuid4()), "matricula_id": escuela.ajeno.matricula.id, "seccion_id": escuela.s5c.id,
        "fecha": "2026-10-06", "estado": "P", "marcado_en": lima(2026, 10, 6, 7, 48).isoformat(),
    }]}, format="json")
    assert r.json()["resultados"][0]["resultado"] == "aplicada"


def test_quitar_permiso_bloquea_la_api(escuela):
    docente = Rol.objects.get(codigo="DOCENTE")
    docente.permisos = [p for p in docente.permisos if p != "estudiantes.ver_historial"]
    docente.save()
    c = cliente_de(Usuario.objects.get(pk=escuela.marisol.pk))
    assert c.get(f"/api/v1/estudiantes/{escuela.mateo.estudiante.id}/historial/").status_code == 403


def test_eliminar_roles(admin):
    c = cliente(admin)
    sistema = Rol.objects.get(codigo="AUXILIAR")
    c.post(f"/panel/usuarios/roles/{sistema.pk}/", {"accion": "eliminar"})
    assert Rol.objects.filter(pk=sistema.pk).exists()

    con_usuarios = Rol.objects.create(codigo="TEMP", nombre="Temporal", permisos=["panel.reportes"])
    crear_usuario("t@ie.edu.pe", "TEMP")
    c.post(f"/panel/usuarios/roles/{con_usuarios.pk}/", {"accion": "eliminar"})
    assert Rol.objects.filter(pk=con_usuarios.pk).exists()

    vacio = Rol.objects.create(codigo="VACIO", nombre="Vacío")
    c.post(f"/panel/usuarios/roles/{vacio.pk}/", {"accion": "eliminar"})
    assert not Rol.objects.filter(pk=vacio.pk).exists()


def test_no_se_queda_sin_administrador(admin):
    c = cliente(admin)
    r = c.post(f"/panel/usuarios/{admin.pk}/", {
        "nombres": admin.nombres, "apellidos": admin.apellidos, "email": admin.email,
        "rol": "DOCENTE", "is_active": "on",
    })
    assert "único administrador" in r.content.decode()
    admin.refresh_from_db()
    assert admin.rol_id == "ADMIN"
    # El administrador conserva todos los permisos aunque se intente vaciar su rol
    rol_admin = Rol.objects.get(codigo="ADMIN")
    c.post(f"/panel/usuarios/roles/{rol_admin.pk}/", {"nombre": "Administrador", "permisos": []})
    assert Usuario.objects.get(pk=admin.pk).puede("panel.usuarios")


def test_rol_con_permiso_docente_aparece_como_tutor(admin, escuela):
    Rol.objects.create(codigo="DOCENTE_AREA", nombre="Docente de área", permisos=["app.acceso", "academico.docente"])
    nuevo = crear_usuario("area@ie.edu.pe", "DOCENTE_AREA", "Pedro", "Inglés")
    html = cliente(admin).get(f"/panel/secciones/{escuela.s3b.pk}/").content.decode()
    assert f'value="{nuevo.pk}"' in html
    assert cliente(admin).get(f"/panel/docentes/{nuevo.pk}/").status_code == 200


def test_niveles_y_grados(admin):
    c = cliente(admin)
    c.get("/panel/configuracion/niveles/")
    secundaria = Nivel.objects.get(nombre="SECUNDARIA")
    assert not secundaria.activo
    c.post("/panel/configuracion/niveles/", {"accion": "nivel", "nivel_id": secundaria.pk, "activo": "1"})
    secundaria.refresh_from_db()
    assert secundaria.activo
    c.post("/panel/configuracion/niveles/", {"accion": "crear_grado", "nivel": secundaria.pk, "numero": 1, "nombre": "1.º año", "orden": 7})
    assert Grado.objects.filter(nivel=secundaria, nombre="1.º año").exists()
    # No se puede dejar sin niveles activos
    for n in Nivel.objects.filter(activo=True):
        c.post("/panel/configuracion/niveles/", {"accion": "nivel", "nivel_id": n.pk, "activo": "0"})
    assert Nivel.objects.filter(activo=True).count() == 1


def png(color="#14213D"):
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, "PNG")
    buf.seek(0)
    buf.name = "logo.png"
    return buf


def test_institucion_nombre_y_logo_dinamicos(admin, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    c = cliente(admin)
    r = c.post("/panel/configuracion/", {
        "accion": "institucion", "nombre": "I.E. N.º 50001 San Martín", "nombre_corto": "San Martín",
        "codigo_modular": "1234567", "logo": png(), "imagen_portada": png("#1E7A4C"),
    })
    assert r.status_code == 302
    inst = Institucion.obtener()
    assert inst.nombre == "I.E. N.º 50001 San Martín" and inst.logo and inst.imagen_portada

    api = APIClient().get("/api/v1/institucion/").json()
    assert api["nombre"] == "I.E. N.º 50001 San Martín" and api["nombre_corto"] == "San Martín"
    assert "/institucion/logo/?v=" in api["logo_url"] and "/institucion/portada/?v=" in api["portada_url"]
    assert Client().get("/institucion/logo/").status_code == 200

    html = c.get("/panel/usuarios/").content.decode()
    assert "San Martín" in html and "/institucion/logo/?v=" in html
    login = Client().get("/panel/login/").content.decode()
    assert "I.E. N.º 50001 San Martín" in login and "con-portada" in login and "Hora de Lima" not in login


def test_quitar_logo(admin, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    c = cliente(admin)
    c.post("/panel/configuracion/", {"accion": "institucion", "nombre": "I.E. Prueba", "logo": png()})
    assert Institucion.obtener().logo
    c.post("/panel/configuracion/", {"accion": "institucion", "nombre": "I.E. Prueba", "quitar_logo": "on"})
    assert not Institucion.obtener().logo
    assert APIClient().get("/api/v1/institucion/").json()["logo_url"] is None
