from apps.institucion.models import AnioEscolar, Institucion

from .mixins import menu_de


def panel(request):
    """Datos comunes del layout: I.E., año activo, permisos y menú del usuario."""
    if not request.path.startswith("/panel"):
        return {}
    u = request.user
    permisos = u.permisos if u.is_authenticated else set()
    return {
        "institucion": Institucion.obtener(),
        "anio_activo": AnioEscolar.activo_actual(),
        "permisos": permisos,
        "menu_grupos": menu_de(u) if u.is_authenticated else [],
        "menu_items": [o for _, ops in (menu_de(u) if u.is_authenticated else []) for o in ops],
    }
