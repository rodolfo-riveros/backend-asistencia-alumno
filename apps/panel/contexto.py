from apps.institucion.models import AnioEscolar, Institucion

from .mixins import MENU


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
        "menu_items": [m for m in MENU if m[1] in permisos],
    }
