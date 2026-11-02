from django.urls import path
from django.views.generic import RedirectView

from .views import (
    academico, anio, base, carnets, configuracion, dashboard, estudiantes, importar, reportes, usuarios,
)

app_name = "panel"

urlpatterns = [
    path("login/", base.LoginView.as_view(), name="login"),
    path("salir/", base.LogoutView.as_view(), name="logout"),
    path("cambiar-contrasena/", base.CambiarPasswordView.as_view(), name="cambiar_password"),
    path("", dashboard.DashboardView.as_view(), name="dashboard"),
    path("asistencia/", RedirectView.as_view(url="/panel/", query_string=True)),
    # Año escolar y paso de año
    path("anio/", anio.AnioEscolarView.as_view(), name="anio"),
    path("anio/promocion/", anio.PromocionView.as_view(), name="promocion"),
    path("anio/promocion/<int:pk>/", anio.PromocionSeccionView.as_view(), name="promocion_seccion"),
    path("recordar/", dashboard.RecordarDocentesView.as_view(), name="recordar"),
    path("reportes/", reportes.ReportesView.as_view(), name="reportes"),
    # Estudiantes
    path("estudiantes/", estudiantes.EstudiantesView.as_view(), name="estudiantes"),
    path("estudiantes/nuevo/", estudiantes.EstudianteNuevoView.as_view(), name="estudiante_nuevo"),
    path("estudiantes/<int:pk>/", estudiantes.EstudianteView.as_view(), name="estudiante"),
    # Grados y secciones
    path("secciones/", academico.SeccionesView.as_view(), name="secciones"),
    path("secciones/nueva/", academico.SeccionFormView.as_view(), name="seccion_nueva"),
    path("secciones/<int:pk>/", academico.SeccionFormView.as_view(), name="seccion_editar"),
    path("secciones/<int:pk>/eliminar/", academico.SeccionEliminarView.as_view(), name="seccion_eliminar"),
    # Docentes
    path("docentes/", academico.DocentesView.as_view(), name="docentes"),
    path("docentes/nuevo/", academico.DocenteNuevoView.as_view(), name="docente_nuevo"),
    path("docentes/<int:pk>/", academico.DocenteView.as_view(), name="docente"),
    # Cursos y horarios
    path("cursos/", academico.CursosView.as_view(), name="cursos"),
    path("horarios/<int:pk>/", academico.HorarioView.as_view(), name="horario"),
    path("horarios/bloque/<int:pk>/eliminar/", academico.BloqueEliminarView.as_view(), name="bloque_eliminar"),
    # Carnets
    path("carnets/", carnets.CarnetsView.as_view(), name="carnets"),
    path("carnets/seccion/<int:pk>/", carnets.HojaCarnetsView.as_view(), name="carnets_seccion"),
    path("carnets/estudiante/<int:pk>/", carnets.HojaCarnetsView.as_view(por_estudiante=True, permiso="panel.estudiantes"), name="carnet_estudiante"),
    # Importación
    path("importar/", importar.ImportarView.as_view(), name="importar"),
    path("importar/plantilla.xlsx", importar.PlantillaView.as_view(), name="plantilla"),
    # Configuración
    path("configuracion/", configuracion.ConfiguracionView.as_view(), name="configuracion"),
    path("configuracion/calendario/", configuracion.CalendarioView.as_view(), name="calendario"),
    path("secciones/grados/", configuracion.NivelesView.as_view(), name="niveles"),
    # Usuarios, roles y permisos
    path("usuarios/", usuarios.UsuariosView.as_view(), name="usuarios"),
    path("usuarios/nuevo/", usuarios.UsuarioFormView.as_view(), name="usuario_nuevo"),
    path("usuarios/<int:pk>/", usuarios.UsuarioFormView.as_view(), name="usuario"),
    path("usuarios/roles/", usuarios.RolesView.as_view(), name="roles"),
    path("usuarios/roles/nuevo/", usuarios.RolFormView.as_view(), name="rol_nuevo"),
    path("usuarios/roles/<int:pk>/", usuarios.RolFormView.as_view(), name="rol"),
]
