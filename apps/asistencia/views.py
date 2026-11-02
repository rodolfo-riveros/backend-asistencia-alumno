import hashlib
import json
from datetime import datetime, timedelta

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.academico import acceso
from apps.academico.models import BloqueHorario, Seccion
from apps.comun.excepciones import ErrorNegocio
from apps.comun.fechas import ahora_lima, fecha_larga, hora_corta, hora_texto, hoy_lima
from apps.comun.permisos import EsDocenteDeLaSeccion, PuedeJustificar, PuedePasarLista
from apps.cuentas.views import datos_turno
from apps.estudiantes.models import Carnet, Matricula
from apps.institucion.models import AnioEscolar, Configuracion, Turno
from apps.reportes.servicios import resumen_sesion

from . import servicios
from .models import Registro
from .serializers import CerrarSerializer, EscanearSerializer, JustificarSerializer, LoteSerializer, MarcaSerializer


def turno_actual():
    """El turno cuyo ingreso está más cerca (desde 90 min antes)."""
    turnos = list(Turno.objects.all())
    if not turnos:
        return None
    ahora = ahora_lima()
    actual = turnos[0]
    for t in turnos:
        inicio = (datetime.combine(ahora.date(), t.hora_ingreso) - timedelta(minutes=90)).time()
        if ahora.time() >= inicio:
            actual = t
    return actual


def datos_registro(r: Registro | None):
    if r is None:
        return None
    jus = getattr(r, "justificacion", None)
    return {
        "id": r.id,
        "estado": r.estado,
        "estado_original": r.estado_original or None,
        "metodo": r.metodo,
        "marcado_en": r.marcado_en.isoformat(),
        "hora": hora_texto(r.marcado_en),
        "hora_corregida": r.hora_corregida,
        "justificacion": {
            "motivo": jus.motivo,
            "motivo_texto": jus.get_motivo_display(),
            "detalle": jus.detalle,
            "tiene_foto": bool(jus.foto),
        } if jus else None,
    }


def _bloque(seccion, bloque_id):
    if not bloque_id:
        return None
    return get_object_or_404(BloqueHorario.objects.select_related("asignacion__curso"), pk=bloque_id, seccion=seccion)


# --------------------------------------------------------------------------
# GET movil/hoy/  → tarjetas de "Mis secciones"
# --------------------------------------------------------------------------
class HoyView(APIView):
    def get(self, request):
        u = request.user
        hoy = hoy_lima()
        config = Configuracion.obtener()
        no_lectivo = servicios.motivo_no_lectivo(hoy)

        tarjetas = []
        todas = u.puede("asistencia.todas_las_secciones")
        if todas or u.puede("asistencia.pasar_lista"):
            diarias = acceso.secciones_visibles(u)
            if not todas:
                diarias = diarias.filter(tutor=u)
            for s in diarias:
                tarjetas.append(self._tarjeta(s, hoy, None))
            if config.permite_bloques and u.puede("asistencia.pasar_lista"):
                bloques = BloqueHorario.objects.filter(
                    asignacion__docente=u, dia_semana=hoy.isoweekday(), seccion__anio_escolar=AnioEscolar.activo_actual()
                ).select_related("seccion__grado__nivel", "seccion__turno", "asignacion__curso")
                for b in bloques:
                    tarjetas.append(self._tarjeta(b.seccion, hoy, b))

        turno = tarjetas and Seccion.objects.get(pk=tarjetas[0]["seccion_id"]).turno or turno_actual()
        respuesta = {
            "fecha": hoy.isoformat(),
            "fecha_texto": fecha_larga(hoy),
            "hora_servidor": timezone.now().isoformat(),
            "es_dia_lectivo": no_lectivo is None,
            "motivo_no_lectivo": no_lectivo,
            "turno": datos_turno(turno) if turno else None,
            "tarjetas": tarjetas,
        }
        if u.puede("asistencia.escanear_puerta") or todas:
            respuesta["escaneados_hoy"] = Registro.objects.filter(sesion__fecha=hoy, metodo=Registro.Metodo.QR).count()
        return Response(respuesta)

    def _tarjeta(self, s, hoy, bloque):
        nivel = s.grado.nivel.get_nombre_display()
        tarjeta = {
            "tipo": "BLOQUE" if bloque else "DIARIA",
            "seccion_id": s.id,
            "bloque_id": bloque.id if bloque else None,
            "grado": s.grado.corto,
            "letra": s.letra,
            "nombre": s.nombre_largo,
            "curso": None,
            "horario": None,
            **resumen_sesion(s, hoy, bloque),
        }
        tarjeta["subtitulo"] = f"{nivel} · {s.turno.get_nombre_display()} · {tarjeta['total']} estudiantes"
        if bloque:
            tarjeta["curso"] = bloque.asignacion.curso.nombre
            tarjeta["horario"] = f"{hora_corta(bloque.hora_inicio)}–{hora_corta(bloque.hora_fin)}"
            tarjeta["nombre"] = f"{bloque.asignacion.curso.nombre} · {s.nombre_corto} · {tarjeta['horario']}"
        return tarjeta


# --------------------------------------------------------------------------
# GET movil/nomina/  → caché offline (con ETag)
# --------------------------------------------------------------------------
class NominaView(APIView):
    def get(self, request):
        u = request.user
        secciones = acceso.secciones_visibles(u)
        if turno := request.query_params.get("turno"):
            secciones = secciones.filter(turno__nombre=turno.upper())

        hashes = dict(
            Carnet.objects.filter(estado=Carnet.Estado.ACTIVO).values_list("estudiante_id", "token_hash")
        )
        datos = []
        for s in secciones:
            matriculas = (
                Matricula.objects.filter(seccion=s, estado=Matricula.Estado.ACTIVA)
                .select_related("estudiante")
                .order_by("estudiante__apellido_paterno", "estudiante__apellido_materno", "estudiante__nombres")
            )
            datos.append({
                **servicios.datos_seccion(s),
                "turno_id": s.turno_id,
                "es_tutor": s.tutor_id == u.id,
                "puede_marcar": acceso.puede_marcar(u, s, None, "MANUAL"),
                "puede_escanear": acceso.puede_marcar(u, s, None, "QR"),
                "estudiantes": [
                    {
                        "matricula_id": m.id,
                        "estudiante_id": m.estudiante_id,
                        "codigo": m.estudiante.codigo_estudiante,
                        "apellido_paterno": m.estudiante.apellido_paterno,
                        "apellido_materno": m.estudiante.apellido_materno,
                        "nombres": m.estudiante.nombres,
                        "iniciales": m.estudiante.iniciales,
                        "carnet_hash": hashes.get(m.estudiante_id),
                    }
                    for m in matriculas
                ],
            })

        cuerpo = {
            "turnos": [datos_turno(t) for t in Turno.objects.all()],
            "secciones": datos,
        }
        version = hashlib.sha256(json.dumps(cuerpo, sort_keys=True, default=str).encode()).hexdigest()[:32]
        etag = f'"{version}"'
        if request.headers.get("If-None-Match") == etag:
            return Response(status=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
        return Response({"version": version, "generado_en": timezone.now().isoformat(), **cuerpo}, headers={"ETag": etag})


# --------------------------------------------------------------------------
# GET secciones/{id}/sesion/  → pase de lista
# --------------------------------------------------------------------------
class SesionSeccionView(APIView):
    permission_classes = [PuedePasarLista, EsDocenteDeLaSeccion]

    def get(self, request, pk):
        seccion = get_object_or_404(Seccion.objects.select_related("grado__nivel", "turno"), pk=pk)
        fecha = _fecha_param(request.query_params.get("fecha"))
        bloque = _bloque(seccion, request.query_params.get("bloque"))
        sesion = servicios.obtener_sesion(seccion, fecha, bloque)

        registros = {}
        if sesion:
            registros = {
                r.matricula_id: r
                for r in Registro.objects.filter(sesion=sesion).select_related("justificacion")
            }
        matriculas = (
            Matricula.objects.filter(seccion=seccion, estado=Matricula.Estado.ACTIVA)
            .select_related("estudiante")
            .order_by("estudiante__apellido_paterno", "estudiante__apellido_materno", "estudiante__nombres")
        )
        u = request.user
        puede = acceso.puede_marcar(u, seccion, bloque)
        return Response({
            "seccion": servicios.datos_seccion(seccion),
            "bloque": {"id": bloque.id, "curso": bloque.asignacion.curso.nombre} if bloque else None,
            "fecha": fecha.isoformat(),
            "fecha_texto": fecha_larga(fecha),
            "es_dia_lectivo": servicios.motivo_no_lectivo(fecha, seccion.anio_escolar) is None,
            "sesion": {
                "id": sesion.id,
                "estado": sesion.estado,
                "cerrada_en": sesion.cerrada_en.isoformat() if sesion.cerrada_en else None,
            } if sesion else None,
            "editable": puede and (u.puede("asistencia.editar_fechas_pasadas") or fecha == hoy_lima()),
            "turno": datos_turno(seccion.turno),
            "contadores": resumen_sesion(seccion, fecha, bloque),
            "estudiantes": [
                {
                    "matricula_id": m.id,
                    "estudiante_id": m.estudiante_id,
                    "apellidos": m.estudiante.apellidos,
                    "nombres": m.estudiante.nombres,
                    "iniciales": m.estudiante.iniciales,
                    "registro": datos_registro(registros.get(m.id)),
                }
                for m in matriculas
            ],
        })


class CerrarSesionView(APIView):
    permission_classes = [PuedePasarLista, EsDocenteDeLaSeccion]

    def post(self, request, pk):
        seccion = get_object_or_404(Seccion, pk=pk)
        datos = CerrarSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        fecha = datos.validated_data["fecha"] or hoy_lima()
        bloque = _bloque(seccion, datos.validated_data["bloque_id"])
        u = request.user
        if not acceso.puede_marcar(u, seccion, bloque) or (
            not u.puede("asistencia.editar_fechas_pasadas") and fecha != hoy_lima()
        ):
            raise ErrorNegocio("No puedes guardar esta lista.", "sin_permiso", status_code=403)
        sesion = servicios.cerrar_sesion(u, seccion, fecha, bloque)
        return Response({
            "sesion": {"id": sesion.id, "estado": sesion.estado, "cerrada_en": sesion.cerrada_en.isoformat()},
            "contadores": resumen_sesion(seccion, fecha, bloque),
        })


# --------------------------------------------------------------------------
# POST asistencia/lote/  → envío de la cola offline (idempotente)
# --------------------------------------------------------------------------
class LoteView(APIView):
    def post(self, request):
        lote = LoteSerializer(data=request.data)
        lote.is_valid(raise_exception=True)
        resultados = []
        for crudo in lote.validated_data["marcas"]:
            marca = MarcaSerializer(data=crudo)
            if not marca.is_valid():
                resultados.append({
                    "uuid_cliente": crudo.get("uuid_cliente"),
                    "resultado": "rechazada",
                    "codigo": "VALIDACION",
                    "detalle": json.dumps(marca.errors, ensure_ascii=False),
                    "registro_id": None,
                    "estado_final": None,
                })
                continue
            d = marca.validated_data
            res = servicios.aplicar_marca(
                request.user,
                matricula_id=d["matricula_id"],
                seccion_id=d["seccion_id"],
                fecha=d["fecha"],
                bloque_id=d["bloque_id"],
                estado=d["estado"],
                metodo=d["metodo"],
                marcado_en=d["marcado_en"],
                uuid_cliente=d["uuid_cliente"],
                dispositivo_id=d["dispositivo_id"],
                justificacion=d["justificacion"],
                motivo_cambio=d["motivo_cambio"],
            )
            resultados.append(res.como_dict())
        return Response({"resultados": resultados})


# --------------------------------------------------------------------------
# POST asistencia/escanear/
# --------------------------------------------------------------------------
class EscanearView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "escanear"

    def post(self, request):
        datos = EscanearSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        return Response(servicios.escanear(request.user, **datos.validated_data))


# --------------------------------------------------------------------------
# POST registros/{id}/justificar/   ·   GET registros/{id}/justificacion/foto/
# --------------------------------------------------------------------------
def _registro_visible(usuario, pk):
    registro = get_object_or_404(
        Registro.objects.select_related("sesion__seccion", "sesion__bloque__asignacion", "matricula"), pk=pk
    )
    if not acceso.secciones_visibles(usuario).filter(pk=registro.sesion.seccion_id).exists():
        raise Http404
    return registro


class JustificarView(APIView):
    permission_classes = [PuedeJustificar]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk):
        registro = _registro_visible(request.user, pk)
        datos = JustificarSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        servicios.justificar(
            request.user, registro,
            motivo=datos.validated_data["motivo"],
            detalle=datos.validated_data["detalle"],
            foto=datos.validated_data["foto"],
        )
        registro.refresh_from_db()
        return Response(datos_registro(registro), status=status.HTTP_200_OK)


class FotoJustificacionView(APIView):
    """Solo el tutor de la sección y dirección ven la constancia (datos de menores)."""

    def get(self, request, pk):
        registro = _registro_visible(request.user, pk)
        jus = getattr(registro, "justificacion", None)
        if not jus or not jus.foto:
            raise Http404
        if not acceso.puede_ver_apoderado(request.user, registro.sesion.seccion):
            raise ErrorNegocio("No tienes permiso para ver la constancia.", "sin_permiso", status_code=403)
        return FileResponse(jus.foto.open("rb"), content_type="image/jpeg")


def _fecha_param(valor):
    if not valor:
        return hoy_lima()
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        raise ErrorNegocio("Fecha inválida (usa AAAA-MM-DD).", "fecha_invalida")
