from rest_framework.permissions import BasePermission

from apps.academico.acceso import secciones_visibles


class _Permiso(BasePermission):
    """Exige que el rol del usuario tenga alguno de `permisos`."""

    permisos: tuple = ()
    message = "Tu rol no tiene permiso para esta acción."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and any(u.puede(p) for p in self.permisos))


class PuedePasarLista(_Permiso):
    permisos = ("asistencia.pasar_lista", "asistencia.todas_las_secciones")


class PuedeJustificar(_Permiso):
    permisos = ("asistencia.justificar",)


class PuedeVerHistorial(_Permiso):
    permisos = ("estudiantes.ver_historial",)


class EsDocenteDeLaSeccion(BasePermission):
    """La sección de la URL (kwarg 'pk') debe estar entre las del usuario."""

    message = "Esta sección no está entre tus asignaciones."

    def has_permission(self, request, view):
        pk = view.kwargs.get("pk")
        return bool(request.user and request.user.is_authenticated and secciones_visibles(request.user).filter(pk=pk).exists())
