"""Catálogo de permisos y roles iniciales.

Los roles se crean y editan desde el panel (Usuarios → Roles y permisos).
El código nunca pregunta por el nombre del rol: pregunta `usuario.puede("permiso")`.
"""

# (código, grupo, nombre, descripción)
PERMISOS = [
    ("panel.anio_escolar", "Panel web", "Año escolar", "Crear y activar años escolares y pasar a los estudiantes de año."),
    ("panel.dashboard", "Panel web", "Asistencia del día", "Ver la asistencia del día y enviar recordatorios."),
    ("panel.reportes", "Panel web", "Reportes", "Reportes diarios y mensuales, % por estudiante, alertas y exportes."),
    ("panel.estudiantes", "Panel web", "Estudiantes", "Fichas, apoderados, matrículas y carnet de cada estudiante."),
    ("panel.secciones", "Panel web", "Grados y secciones", "Crear y editar secciones y tutores."),
    ("panel.docentes", "Panel web", "Docentes y asignaciones", "Crear docentes, tutorías y cursos asignados."),
    ("panel.cursos", "Panel web", "Cursos y horarios", "Catálogo de cursos y horario semanal."),
    ("panel.carnets", "Panel web", "Carnets QR", "Imprimir y emitir carnets por sección."),
    ("panel.importar", "Panel web", "Importar estudiantes", "Cargar la nómina desde Excel o SIAGIE."),
    ("panel.calendario", "Panel web", "Calendario", "Feriados, vacaciones y días sin clases."),
    ("panel.configuracion", "Panel web", "Configuración", "Datos de la I.E., logo, turnos, reglas, años, niveles y grados."),
    ("panel.usuarios", "Panel web", "Usuarios, roles y permisos", "Crear usuarios, roles y decidir qué puede hacer cada uno."),
    ("app.acceso", "App móvil", "Ingresar a la app", "Puede iniciar sesión en la app del teléfono."),
    ("asistencia.pasar_lista", "App móvil", "Pasar lista", "Registrar asistencia en sus secciones (como tutor o docente de curso)."),
    ("asistencia.escanear_puerta", "App móvil", "Escanear en la puerta", "Registrar el ingreso de cualquier estudiante escaneando su carnet."),
    ("asistencia.todas_las_secciones", "App móvil", "Todas las secciones", "Ver y registrar asistencia en todas las secciones."),
    ("asistencia.justificar", "App móvil", "Justificar", "Justificar faltas y tardanzas."),
    ("asistencia.editar_fechas_pasadas", "App móvil", "Corregir días anteriores", "Modificar la asistencia de días pasados (con motivo)."),
    ("estudiantes.ver_historial", "App móvil", "Historial de estudiantes", "Buscar estudiantes y ver su historial del mes."),
    ("estudiantes.ver_apoderado", "App móvil", "Contactar apoderados", "Ver el celular del apoderado y llamarlo."),
    ("academico.docente", "Académico", "Es docente", "Puede ser tutor de una sección y tener cursos asignados."),
]
CODIGOS = [p[0] for p in PERMISOS]
GRUPOS = list(dict.fromkeys(p[1] for p in PERMISOS))

ROL_ADMIN = "ADMIN"

_DIRECCION = [c for c in CODIGOS if c not in ("panel.configuracion", "panel.usuarios", "academico.docente", "asistencia.escanear_puerta")]

ROLES_INICIALES = {
    # código: (nombre, descripción, permisos)
    "ADMIN": ("Administrador", "Acceso total al sistema.", CODIGOS),
    "DIRECTOR": ("Director(a)", "Todo lo académico y los reportes.", _DIRECCION),
    "DOCENTE": (
        "Docente",
        "Pasa lista en la app de sus secciones.",
        ["app.acceso", "asistencia.pasar_lista", "asistencia.justificar", "estudiantes.ver_historial",
         "estudiantes.ver_apoderado", "academico.docente"],
    ),
    "AUXILIAR": ("Auxiliar", "Escanea el ingreso en la puerta.", ["app.acceso", "asistencia.escanear_puerta"]),
}


def agrupados():
    """[(grupo, [(codigo, nombre, descripcion), …]), …] para dibujar la matriz de permisos."""
    return [(g, [(c, n, d) for c, gg, n, d in PERMISOS if gg == g]) for g in GRUPOS]


def roles_con(permiso: str) -> list[str]:
    """Códigos de los roles que tienen un permiso (para filtrar usuarios)."""
    from .models import Rol

    return [r.codigo for r in Rol.objects.all() if r.codigo == ROL_ADMIN or permiso in r.permisos]
