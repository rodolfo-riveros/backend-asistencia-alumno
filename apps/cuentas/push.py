"""Notificaciones push con el servicio de Expo (exponent_server_sdk)."""

import logging

from exponent_server_sdk import (
    DeviceNotRegisteredError, PushClient, PushMessage, PushServerError, PushTicketError,
)
from requests.exceptions import ConnectionError, HTTPError, Timeout

log = logging.getLogger(__name__)


def enviar_push(usuarios, titulo: str, cuerpo: str, datos: dict | None = None) -> dict:
    """Envía a quienes tienen token de Expo. Devuelve {"enviados", "sin_app", "errores"}."""
    resumen = {"enviados": 0, "sin_app": 0, "errores": 0}
    mensajes, destinatarios = [], []
    for u in usuarios:
        if u.expo_push_token and PushClient.is_exponent_push_token(u.expo_push_token):
            mensajes.append(PushMessage(to=u.expo_push_token, title=titulo, body=cuerpo, data=datos or {}, sound="default"))
            destinatarios.append(u)
        else:
            resumen["sin_app"] += 1
    if not mensajes:
        return resumen

    try:
        tickets = PushClient().publish_multiple(mensajes)
    except (PushServerError, ConnectionError, HTTPError, Timeout) as e:
        log.warning("push: error del servicio de Expo: %s", type(e).__name__)
        resumen["errores"] += len(mensajes)
        return resumen

    for u, ticket in zip(destinatarios, tickets):
        try:
            ticket.validate_response()
            resumen["enviados"] += 1
        except DeviceNotRegisteredError:
            # La app se desinstaló o cerró sesión: se olvida el token.
            u.expo_push_token = ""
            u.save(update_fields=["expo_push_token"])
            resumen["sin_app"] += 1
        except PushTicketError:
            log.warning("push: ticket con error para usuario %s", u.id)
            resumen["errores"] += 1
    return resumen
