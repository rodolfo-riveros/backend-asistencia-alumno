from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.asistencia.reglas import formatear_porcentaje

register = template.Library()

# Trazos estilo Lucide, tomados del diseño.
ICONOS = {
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "reportes": '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
    "estudiantes": '<circle cx="9" cy="8" r="4"/><path d="M2 21c1-4 3.8-6 7-6s6 2 7 6"/><path d="M16 4a4 4 0 010 8"/><path d="M19 15c1.5.7 2.5 2.5 3 6"/>',
    "secciones": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18"/><path d="M9 10v10"/>',
    "docentes": '<path d="M4 19V6l8-3 8 3v13"/><path d="M9 21v-6h6v6"/>',
    "horarios": '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l2.5 2"/>',
    "carnets": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><path d="M14 14h3v3h-3z"/><path d="M21 14v7h-7"/>',
    "importar": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 21h16"/>',
    "descargar": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 21h16"/>',
    "configuracion": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>',
    "escudo": '<path d="M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6l8-3z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "mas": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "buscar": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "volver": '<path d="M15 18l-6-6 6-6"/>',
    "imprimir": '<path d="M6 9V3h12v6"/><rect x="4" y="9" width="16" height="8" rx="2"/><path d="M8 14h8v7H8z"/>',
    "check": '<path d="M5 12l5 5 9-10"/>',
    "usuarios": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    "cerrar": '<path d="M6 6l12 12"/><path d="M18 6L6 18"/>',
    "documento": '<path d="M7 3h7l4 4v14H7z"/><path d="M10 13h5"/>',
    "alerta": '<circle cx="12" cy="12" r="8"/><path d="M12 8v5"/><path d="M12 16h.01"/>',
    "inicio": '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    "anio": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18"/><path d="M8 3v4"/><path d="M16 3v4"/><path d="M8 14h3v3H8z"/>',
    "flecha": '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "copiar": '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 00-2-2H5a2 2 0 00-2 2v9a2 2 0 002 2h3"/>',
    "calendario": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18"/><path d="M8 3v4"/><path d="M16 3v4"/>',
}


@register.simple_tag
def icono(nombre, tam=18, color="currentColor", grosor=2):
    return format_html(
        '<svg width="{}" height="{}" viewBox="0 0 24 24" fill="none" stroke="{}" stroke-width="{}" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>',
        tam, tam, color, grosor, mark_safe(ICONOS.get(nombre, "")),
    )


@register.inclusion_tag("panel/parciales/campo.html")
def campo(field, ancho=False, ayuda=None):
    return {"field": field, "ancho": ancho, "ayuda": ayuda or field.help_text}


@register.filter
def clase_estado(valor):
    """Chip para estados de matrícula/carnet."""
    return {
        "ACTIVA": "ok", "ACTIVO": "ok", "RETIRADO": "error", "TRASLADADO": "aviso",
        "REVOCADO": "", "BAJA": "error",
    }.get(valor, "")


@register.filter
def iniciales(texto):
    partes = (texto or "").split()
    return "".join(p[0] for p in partes[:2]).upper()


@register.filter
def pct(valor):
    """92.9 → '92,9 %' (y '—' si no hay datos)."""
    return formatear_porcentaje(valor)


ESTILO_ESTADO = {"P": "p", "T": "t", "F": "f", "J": "j"}


@register.filter
def celda(estado):
    """Clase CSS de la celda de la matriz mensual."""
    return f"celda-{ESTILO_ESTADO[estado]}" if estado in ESTILO_ESTADO else "celda-vacia"


_NOMBRES_PERMISOS = None


@register.filter
def nombre_permiso(codigo):
    global _NOMBRES_PERMISOS
    if _NOMBRES_PERMISOS is None:
        from apps.cuentas.permisos import PERMISOS

        _NOMBRES_PERMISOS = {c: f"{g} · {n}" for c, g, n, _ in PERMISOS}
    return _NOMBRES_PERMISOS.get(codigo, codigo)
