import pytest
from rest_framework.test import APIClient

from conftest import cliente_de

pytestmark = pytest.mark.django_db


def login(email, password):
    return APIClient().post("/api/v1/auth/login/", {"email": email, "password": password}, format="json")


def test_login_correcto_devuelve_tokens(escuela):
    r = login("M.Quispe@ie-ejemplo.edu.pe", "clave-segura-123")
    assert r.status_code == 200
    data = r.json()
    assert data["access"] and data["refresh"] and data["usuario"]["nombre_corto"] == "Marisol"


def test_login_incorrecto_y_bloqueo_tras_5_intentos(escuela):
    for _ in range(5):
        r = login("m.quispe@ie-ejemplo.edu.pe", "mala")
        assert r.status_code == 401 and r.json()["codigo"] == "credenciales_invalidas"
    r = login("m.quispe@ie-ejemplo.edu.pe", "clave-segura-123")
    assert r.status_code == 403 and r.json()["codigo"] == "cuenta_bloqueada"


def test_me_y_errores_en_espanol(escuela):
    assert APIClient().get("/api/v1/me/").json() == {"detalle": "Debes iniciar sesión.", "codigo": "not_authenticated"}
    data = cliente_de(escuela.marisol).get("/api/v1/me/").json()
    assert data["usuario"]["rol"] == "DOCENTE"
    assert data["secciones"][0]["nombre_corto"] == "3.º B"


def test_logout_invalida_refresh(escuela):
    tokens = login("m.quispe@ie-ejemplo.edu.pe", "clave-segura-123").json()
    c = cliente_de(escuela.marisol)
    assert c.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}, format="json").status_code == 204
    r = APIClient().post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert r.status_code == 401


def test_cambiar_password(escuela):
    escuela.marisol.debe_cambiar_password = True
    escuela.marisol.save()
    c = cliente_de(escuela.marisol)
    r = c.post("/api/v1/auth/cambiar-password/", {"actual": "clave-segura-123", "nueva": "Nueva-clave-2026"}, format="json")
    assert r.status_code == 200
    escuela.marisol.refresh_from_db()
    assert escuela.marisol.debe_cambiar_password is False
