from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

# Menú lateral agrupado en el orden de trabajo: primero se organiza el año, luego las
# personas y recién después se toma y revisa la asistencia.
# Cada opción: (clave, permiso, url, texto, ícono). permiso None = cualquier usuario del panel.
MENU_GRUPOS = [
    ("", [
        ("dashboard", "panel.dashboard", "panel:dashboard", "Inicio", "dashboard"),
    ]),
    ("Organización del año", [
        ("anio", "panel.anio_escolar", "panel:anio", "Año escolar", "anio"),
        ("secciones", "panel.secciones", "panel:secciones", "Grados y secciones", "secciones"),
        ("cursos", "panel.cursos", "panel:cursos", "Cursos y horarios", "horarios"),
        ("calendario", "panel.calendario", "panel:calendario", "Calendario", "calendario"),
    ]),
    ("Personas", [
        ("docentes", "panel.docentes", "panel:docentes", "Docentes", "docentes"),
        ("estudiantes", "panel.estudiantes", "panel:estudiantes", "Estudiantes", "estudiantes"),
        ("importar", "panel.importar", "panel:importar", "Importar estudiantes", "importar"),
        ("carnets", "panel.carnets", "panel:carnets", "Carnets QR", "carnets"),
    ]),
    ("Asistencia", [
        ("reportes", "panel.reportes", "panel:reportes", "Reportes", "reportes"),
    ]),
    ("Sistema", [
        ("usuarios", "panel.usuarios", "panel:usuarios", "Usuarios y roles", "usuarios"),
        ("configuracion", "panel.configuracion", "panel:configuracion", "Institución y reglas", "configuracion"),
    ]),
]
MENU = [opcion for _, opciones in MENU_GRUPOS for opcion in opciones]


def menu_de(usuario) -> list[tuple[str, list]]:
    """Grupos del menú con solo las opciones que el usuario puede ver."""
    salida = []
    for titulo, opciones in MENU_GRUPOS:
        visibles = [o for o in opciones if o[1] is None or usuario.puede(o[1])]
        if visibles:
            salida.append((titulo, visibles))
    return salida


def primera_pagina(usuario) -> str | None:
    """URL de la primera sección del panel que el usuario puede ver."""
    for _, permiso, url, _, _ in MENU:
        if permiso is None or usuario.puede(permiso):
            return url
    return None


class PanelMixin(LoginRequiredMixin):
    """Exige `permiso` (del rol del usuario). `menu` marca la opción activa de la barra lateral."""

    login_url = reverse_lazy("panel:login")
    menu = ""
    permiso: str | None = None  # None = basta con tener acceso al panel

    def dispatch(self, request, *args, **kwargs):
        u = request.user
        if not u.is_authenticated:
            return self.handle_no_permission()
        if not u.acceso_panel or (self.permiso and not u.puede(self.permiso)):
            return render(request, "panel/403.html", {"menu": self.menu}, status=403)
        if u.debe_cambiar_password and request.resolver_match.url_name != "cambiar_password":
            return redirect("panel:cambiar_password")
        return super().dispatch(request, *args, **kwargs)

    def render(self, plantilla, ctx=None, status=200):
        return render(self.request, plantilla, {"menu": self.menu, **(ctx or {})}, status=status)

    @property
    def es_htmx(self):
        return self.request.headers.get("HX-Request") == "true"
