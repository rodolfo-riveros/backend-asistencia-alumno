from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.asistencia import views as asistencia
from apps.cuentas import views as cuentas
from apps.estudiantes import views as estudiantes
from apps.panel.views.base import logo_institucion, portada_institucion


def health(request):
    return JsonResponse({"estado": "ok", "servicio": "asistencia-escolar"})


api_v1 = [
    path("health/", health),
    path("institucion/", cuentas.InstitucionPublicaView.as_view()),
    # Autenticación
    path("auth/login/", cuentas.LoginView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("auth/logout/", cuentas.LogoutView.as_view()),
    path("auth/cambiar-password/", cuentas.CambiarPasswordView.as_view()),
    path("me/", cuentas.MeView.as_view()),
    path("me/push-token/", cuentas.PushTokenView.as_view()),
    # App móvil
    path("movil/hoy/", asistencia.HoyView.as_view()),
    path("movil/nomina/", asistencia.NominaView.as_view()),
    path("secciones/<int:pk>/sesion/", asistencia.SesionSeccionView.as_view()),
    path("secciones/<int:pk>/sesion/cerrar/", asistencia.CerrarSesionView.as_view()),
    path("asistencia/lote/", asistencia.LoteView.as_view()),
    path("asistencia/escanear/", asistencia.EscanearView.as_view()),
    path("registros/<int:pk>/justificar/", asistencia.JustificarView.as_view()),
    path("registros/<int:pk>/justificacion/foto/", asistencia.FotoJustificacionView.as_view()),
    path("estudiantes/", estudiantes.BuscarEstudiantesView.as_view()),
    path("estudiantes/<int:pk>/historial/", estudiantes.HistorialEstudianteView.as_view()),
]

admin.site.site_header = "Asistencia Escolar · Administración"
admin.site.site_title = "Asistencia Escolar"
admin.site.index_title = "Panel de depuración"

urlpatterns = [
    path("", RedirectView.as_view(url="/panel/", permanent=False)),
    path("panel/", include("apps.panel.urls")),
    path("institucion/logo/", logo_institucion, name="logo_institucion"),
    path("institucion/portada/", portada_institucion, name="portada_institucion"),
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
]
