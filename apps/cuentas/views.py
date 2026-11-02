from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.academico.acceso import secciones_visibles
from apps.asistencia.servicios import datos_seccion
from apps.comun.excepciones import ErrorNegocio
from apps.comun.fechas import hora_corta
from apps.institucion.models import AnioEscolar, Configuracion, Institucion, Turno

from .serializers import CambiarPasswordSerializer, LoginSerializer, PushTokenSerializer

Usuario = get_user_model()


def datos_usuario(u):
    return {
        "id": u.id,
        "email": u.email,
        "nombres": u.nombres,
        "apellidos": u.apellidos,
        "nombre_completo": u.nombre_completo,
        "nombre_corto": u.nombre_corto,
        "iniciales": u.iniciales,
        "rol": u.rol_id,
        "rol_texto": u.rol.nombre,
        "permisos": sorted(u.permisos),
        "celular": u.celular,
        "debe_cambiar_password": u.debe_cambiar_password,
    }


def datos_turno(t: Turno):
    return {
        "id": t.id,
        "nombre": t.nombre,
        "nombre_texto": t.get_nombre_display(),
        "hora_ingreso": t.hora_ingreso.strftime("%H:%M"),
        "hora_ingreso_texto": hora_corta(t.hora_ingreso),
        "tolerancia_min": t.tolerancia_min,
        "tarde_desde": t.tarde_desde.strftime("%H:%M"),
        "tarde_desde_texto": hora_corta(t.tarde_desde),
        "hora_limite_falta": t.limite_falta.strftime("%H:%M"),
    }


def datos_institucion(request):
    inst = Institucion.obtener()
    anio = AnioEscolar.activo_actual()
    return {
        "nombre": inst.nombre,
        "nombre_corto": inst.nombre_visible,
        "codigo_modular": inst.codigo_modular,
        "direccion": inst.direccion,
        "telefono": inst.telefono,
        "correo": inst.correo,
        "logo_url": f"{request.build_absolute_uri(reverse('logo_institucion'))}?v={inst.version_imagenes}" if inst.logo else None,
        "portada_url": (
            f"{request.build_absolute_uri(reverse('portada_institucion'))}?v={inst.version_imagenes}" if inst.imagen_portada else None
        ),
        "anio_escolar": anio.anio if anio else None,
        "zona_horaria": "America/Lima",
    }


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        datos = LoginSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        email = datos.validated_data["email"].lower().strip()
        usuario = Usuario.objects.filter(email__iexact=email).first()

        if usuario and usuario.esta_bloqueado():
            minutos = max(1, int((usuario.bloqueado_hasta - timezone.now()).total_seconds() // 60) + 1)
            raise ErrorNegocio(
                f"Demasiados intentos fallidos. Intenta en {minutos} min.", "cuenta_bloqueada",
                status_code=status.HTTP_403_FORBIDDEN, extra={"minutos": minutos},
            )
        if not usuario or not usuario.is_active or not usuario.check_password(datos.validated_data["password"]):
            if usuario and usuario.is_active:
                usuario.registrar_fallo()
            raise ErrorNegocio(
                "Correo o contraseña incorrectos.", "credenciales_invalidas", status_code=status.HTTP_401_UNAUTHORIZED
            )

        if not usuario.puede("app.acceso"):
            raise ErrorNegocio(
                "Tu rol no tiene acceso a la app. Pide a dirección que lo habilite.", "sin_acceso_app",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        usuario.registrar_exito()
        update_last_login(None, usuario)
        refresh = RefreshToken.for_user(usuario)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "usuario": datos_usuario(usuario),
        })


class LogoutView(APIView):
    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except TokenError:
            pass  # ya expirado o inválido: igual se considera cerrada la sesión
        return Response(status=status.HTTP_204_NO_CONTENT)


class CambiarPasswordView(APIView):
    def post(self, request):
        datos = CambiarPasswordSerializer(data=request.data, context={"request": request})
        datos.is_valid(raise_exception=True)
        usuario = request.user
        if not usuario.check_password(datos.validated_data["actual"]):
            raise ErrorNegocio("La contraseña actual no es correcta.", "password_incorrecta")
        usuario.set_password(datos.validated_data["nueva"])
        usuario.debe_cambiar_password = False
        usuario.save(update_fields=["password", "debe_cambiar_password"])
        return Response({"detalle": "Contraseña actualizada."})


class MeView(APIView):
    def get(self, request):
        u = request.user
        config = Configuracion.obtener()
        secciones = []
        ve_secciones = u.puede("asistencia.pasar_lista") or u.puede("asistencia.todas_las_secciones")
        for s in secciones_visibles(u) if ve_secciones else []:
            secciones.append({**datos_seccion(s), "es_tutor": s.tutor_id == u.id})
        return Response({
            "usuario": datos_usuario(u),
            "institucion": datos_institucion(request),
            "configuracion": {
                "modo_asistencia": config.modo_asistencia,
                "umbral_faltas": config.umbral_faltas,
                "umbral_tardanzas": config.umbral_tardanzas,
            },
            "turnos": [datos_turno(t) for t in Turno.objects.all()],
            "secciones": secciones,
        })


class PushTokenView(APIView):
    def post(self, request):
        datos = PushTokenSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        request.user.expo_push_token = datos.validated_data["token"]
        request.user.save(update_fields=["expo_push_token"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class InstitucionPublicaView(APIView):
    """Datos para la pantalla de login (antes de iniciar sesión)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(datos_institucion(request))
