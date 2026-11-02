from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academico import acceso
from apps.asistencia.servicios import datos_estudiante, datos_seccion
from apps.comun.excepciones import ErrorNegocio
from apps.comun.fechas import mes_texto, sin_tildes, hoy_lima
from apps.comun.permisos import PuedeVerHistorial
from apps.reportes.servicios import historial_mes

from .models import Matricula

LIMITE_BUSQUEDA = 50


def _matriculas_visibles(usuario):
    return Matricula.objects.filter(
        seccion__in=acceso.secciones_visibles(usuario), estado=Matricula.Estado.ACTIVA
    ).select_related("estudiante", "seccion__grado__nivel", "seccion__turno")


class BuscarEstudiantesView(APIView):
    """GET estudiantes/?q=  · solo alumnos de las secciones del usuario. Sin tildes."""

    permission_classes = [PuedeVerHistorial]

    def get(self, request):
        q = sin_tildes(request.query_params.get("q", "").strip())
        seccion_id = request.query_params.get("seccion")
        matriculas = _matriculas_visibles(request.user).order_by(
            "estudiante__apellido_paterno", "estudiante__apellido_materno", "estudiante__nombres"
        )
        if seccion_id:
            matriculas = matriculas.filter(seccion_id=seccion_id)

        resultados = []
        for m in matriculas:
            e = m.estudiante
            texto = sin_tildes(f"{e.apellidos} {e.nombres} {e.codigo_estudiante}")
            if q and not all(parte in texto for parte in q.split()):
                continue
            resultados.append({**datos_estudiante(m), "seccion": datos_seccion(m.seccion)})
            if len(resultados) >= LIMITE_BUSQUEDA:
                break
        return Response({"resultados": resultados})


class HistorialEstudianteView(APIView):
    """GET estudiantes/{id}/historial/?mes=2026-09"""

    permission_classes = [PuedeVerHistorial]

    def get(self, request, pk):
        matricula = _matriculas_visibles(request.user).filter(estudiante_id=pk).first()
        if matricula is None:
            raise Http404
        hoy = hoy_lima()
        anio, mes = hoy.year, hoy.month
        if valor := request.query_params.get("mes"):
            try:
                anio, mes = (int(x) for x in valor.split("-"))
                assert 1 <= mes <= 12
            except (ValueError, AssertionError):
                raise ErrorNegocio("Mes inválido (usa AAAA-MM).", "mes_invalido")

        anterior = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
        siguiente = (anio, mes + 1) if mes < 12 else (anio + 1, 1)
        seccion = matricula.seccion
        ver_apoderado = acceso.puede_ver_apoderado(request.user, seccion)
        apoderado = matricula.estudiante.apoderados.order_by("-es_principal").first() if ver_apoderado else None

        return Response({
            "estudiante": datos_estudiante(matricula),
            "seccion": datos_seccion(seccion),
            "mes": f"{anio:04d}-{mes:02d}",
            "mes_texto": mes_texto(anio, mes),
            "mes_anterior": f"{anterior[0]:04d}-{anterior[1]:02d}",
            "mes_siguiente": f"{siguiente[0]:04d}-{siguiente[1]:02d}" if (siguiente[0], siguiente[1]) <= (hoy.year, hoy.month) else None,
            **historial_mes(matricula, anio, mes, hoy),
            "puede_justificar": acceso.puede_justificar(request.user, seccion),
            "puede_llamar": bool(apoderado and apoderado.celular),
            "apoderado": {
                "nombre": apoderado.nombre,
                "parentesco": apoderado.parentesco,
                "celular": apoderado.celular,
            } if apoderado else None,
        })
