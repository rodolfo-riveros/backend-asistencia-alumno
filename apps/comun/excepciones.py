"""Errores de la API con el formato { "detalle": "...", "codigo": "..." }."""

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

MENSAJES = {
    "not_authenticated": "Debes iniciar sesión.",
    "authentication_failed": "Tu sesión no es válida. Vuelve a iniciar sesión.",
    "token_not_valid": "Tu sesión expiró. Vuelve a iniciar sesión.",
    "permission_denied": "No tienes permiso para esta acción.",
    "not_found": "No encontrado.",
    "method_not_allowed": "Método no permitido.",
    "throttled": "Demasiados intentos. Espera un momento.",
    "parse_error": "La solicitud está mal formada.",
    "unsupported_media_type": "Formato de envío no soportado.",
}


class ErrorNegocio(exceptions.APIException):
    """Error de regla de negocio con código propio."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "error"

    def __init__(self, detalle, codigo="error", status_code=None, extra=None):
        super().__init__(detalle, codigo)
        if status_code:
            self.status_code = status_code
        self.codigo = codigo
        self.extra = extra or {}


def manejador_errores(exc, context):
    respuesta = exception_handler(exc, context)
    if respuesta is None:
        return None

    if isinstance(exc, ErrorNegocio):
        respuesta.data = {"detalle": str(exc.detail), "codigo": exc.codigo, **exc.extra}
        return respuesta

    if isinstance(exc, exceptions.ValidationError):
        respuesta.data = {"detalle": "Revisa los datos enviados.", "codigo": "validacion", "campos": exc.detail}
        return respuesta

    codigo = exc.get_codes() if isinstance(exc, exceptions.APIException) else "error"
    if isinstance(codigo, dict):  # simplejwt: {"detail": ..., "code": "token_not_valid"}
        codigo = codigo.get("code") or codigo.get("detail") or "error"
    if isinstance(codigo, list):
        codigo = "error"
    if codigo not in MENSAJES and isinstance(exc, exceptions.AuthenticationFailed):
        codigo = "authentication_failed"
    detalle = MENSAJES.get(codigo) or (str(exc.detail) if hasattr(exc, "detail") else "Error.")
    if isinstance(exc, exceptions.Throttled) and exc.wait:
        detalle = f"Demasiados intentos. Intenta en {int(exc.wait)} segundos."
    respuesta.data = {"detalle": detalle, "codigo": codigo}
    return respuesta


def error_404(detalle="No encontrado."):
    return Response({"detalle": detalle, "codigo": "not_found"}, status=status.HTTP_404_NOT_FOUND)
