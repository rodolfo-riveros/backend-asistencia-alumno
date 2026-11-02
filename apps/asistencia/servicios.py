"""Servicios de asistencia: aplicar marcas, escanear QR, justificar y cerrar."""

import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from PIL import Image, ImageOps

from apps.academico import acceso
from apps.academico.models import BloqueHorario, Seccion
from apps.comun.fechas import a_lima, hora_texto, hoy_lima
from apps.estudiantes.models import Carnet, Matricula, hash_token, leer_codigo_qr
from apps.institucion.models import AnioEscolar, Configuracion, DiaNoLectivo

from . import reglas
from .models import Estado, Justificacion, MarcaCliente, Registro, RegistroHistorial, SesionAsistencia

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def regla_de(turno) -> reglas.ReglaHora:
    return reglas.ReglaHora(turno.hora_ingreso, turno.tolerancia_min, turno.limite_falta)


def motivo_no_lectivo(fecha: date, anio: AnioEscolar | None = None) -> str | None:
    """None si es día hábil; si no, el motivo en texto."""
    anio = anio or AnioEscolar.activo_actual()
    if anio is None:
        return "No hay año escolar activo"
    if not (anio.fecha_inicio <= fecha <= anio.fecha_fin):
        return "Fuera del año escolar"
    if fecha.weekday() >= 5:
        return "Fin de semana"
    dia = DiaNoLectivo.objects.filter(anio_escolar=anio, fecha=fecha).first()
    if dia:
        return dia.descripcion or dia.get_motivo_display()
    return None


def obtener_sesion(seccion, fecha, bloque=None):
    return SesionAsistencia.objects.filter(seccion=seccion, fecha=fecha, bloque_clave=bloque.id if bloque else 0).first()


def obtener_o_crear_sesion(seccion, fecha, bloque, usuario):
    sesion = obtener_sesion(seccion, fecha, bloque)
    if sesion:
        return sesion
    try:
        with transaction.atomic():
            return SesionAsistencia.objects.create(seccion=seccion, fecha=fecha, bloque=bloque, abierta_por=usuario)
    except IntegrityError:
        return obtener_sesion(seccion, fecha, bloque)


def _historial(registro, sesion, matricula, anterior, nuevo, usuario, motivo=""):
    RegistroHistorial.objects.create(
        registro=registro,
        sesion=sesion,
        matricula=matricula,
        estado_anterior=anterior or "",
        estado_nuevo=nuevo or "",
        cambiado_por=usuario,
        motivo=motivo[:200],
    )


@dataclass
class ResultadoMarca:
    uuid_cliente: str | None
    resultado: str  # aplicada | duplicada | rechazada
    codigo: str = ""
    detalle: str = ""
    registro: Registro | None = None
    estado_final: str | None = None
    extra: dict = field(default_factory=dict)

    def como_dict(self):
        return {
            "uuid_cliente": self.uuid_cliente,
            "resultado": self.resultado,
            "codigo": self.codigo or None,
            "detalle": self.detalle or None,
            "registro_id": self.registro.id if self.registro else None,
            "estado_final": self.estado_final,
            "marcado_en": self.registro.marcado_en.isoformat() if self.registro else None,
        }


MENSAJES_RECHAZO = {
    "SIN_PERMISO": "No puedes registrar asistencia en esta sección.",
    "MATRICULA_INVALIDA": "El estudiante no tiene matrícula activa en esta sección.",
    "FUERA_DE_FECHA": "Solo puedes modificar la asistencia del mismo día.",
    "MOTIVO_REQUERIDO": "Falta el motivo.",
    "DIA_NO_LECTIVO": "No es un día lectivo.",
    "MARCA_ANTIGUA": "Ya hay una marca más reciente para este estudiante.",
    "JUSTIFICADO_POR_DIRECCION": "Dirección ya justificó esta inasistencia.",
    "SECCION_INVALIDA": "La sección o el bloque no existen.",
    "ESTADO_INVALIDO": "Estado no válido (usa P, T, F, J o vacío).",
}


def _rechazo(uuid, codigo, registro=None):
    return ResultadoMarca(
        uuid, "rechazada", codigo, MENSAJES_RECHAZO.get(codigo, codigo), registro, registro.estado if registro else None
    )


# --------------------------------------------------------------------------
# Aplicar una marca (pase de lista, lote offline, escaneo)
# --------------------------------------------------------------------------
def aplicar_marca(
    usuario,
    *,
    matricula_id: int,
    seccion_id: int,
    fecha: date,
    estado: str | None,
    metodo: str = Registro.Metodo.MANUAL,
    marcado_en: datetime | None = None,
    bloque_id: int | None = None,
    uuid_cliente=None,
    dispositivo_id: str = "",
    justificacion: dict | None = None,
    origen: str = Registro.Origen.APP,
    motivo_cambio: str = "",
) -> ResultadoMarca:
    uuid = str(uuid_cliente) if uuid_cliente else None

    # 1) Idempotencia: la misma marca enviada dos veces no se aplica dos veces.
    if uuid:
        previa = MarcaCliente.objects.filter(uuid_cliente=uuid).select_related("registro").first()
        if previa:
            return _repetida(uuid, previa)

    resultado = _evaluar_y_aplicar(
        usuario, uuid, matricula_id, seccion_id, fecha, estado, metodo, marcado_en,
        bloque_id, dispositivo_id, justificacion, origen, motivo_cambio,
    )
    if uuid:
        try:
            with transaction.atomic():
                MarcaCliente.objects.create(
                    uuid_cliente=uuid, usuario=usuario, registro=resultado.registro,
                    resultado=resultado.resultado, codigo=resultado.codigo,
                )
        except IntegrityError:
            previa = MarcaCliente.objects.get(uuid_cliente=uuid)
            return _repetida(uuid, previa)
    return resultado


def _repetida(uuid, previa: MarcaCliente) -> ResultadoMarca:
    registro = previa.registro
    if registro is not None:
        registro.refresh_from_db()
    estado = registro.estado if registro else None
    if previa.resultado == "aplicada":
        return ResultadoMarca(uuid, "duplicada", "YA_RECIBIDA", "Esta marca ya fue recibida.", registro, estado)
    return ResultadoMarca(uuid, previa.resultado, previa.codigo, MENSAJES_RECHAZO.get(previa.codigo, ""), registro, estado)


def _evaluar_y_aplicar(
    usuario, uuid, matricula_id, seccion_id, fecha, estado, metodo, marcado_en,
    bloque_id, dispositivo_id, justificacion, origen, motivo_cambio,
) -> ResultadoMarca:
    seccion = Seccion.objects.select_related("turno").filter(pk=seccion_id).first()
    bloque = BloqueHorario.objects.select_related("asignacion").filter(pk=bloque_id).first() if bloque_id else None
    if seccion is None or (bloque_id and bloque is None):
        return _rechazo(uuid, "SECCION_INVALIDA")
    if not acceso.puede_marcar(usuario, seccion, bloque, metodo):
        return _rechazo(uuid, "SIN_PERMISO")

    matricula = Matricula.objects.filter(
        pk=matricula_id, seccion=seccion, estado=Matricula.Estado.ACTIVA
    ).select_related("estudiante").first()
    if matricula is None:
        return _rechazo(uuid, "MATRICULA_INVALIDA")

    ahora = timezone.now()
    marcado, corregida = reglas.validar_marcado_en(
        marcado_en, ahora, settings.MARCA_TOLERANCIA_PASADO, settings.MARCA_TOLERANCIA_FUTURO
    )

    # Regla 5: el docente solo edita el mismo día; quien tenga el permiso, cualquier fecha con motivo.
    if usuario.puede("asistencia.editar_fechas_pasadas"):
        if fecha > hoy_lima():
            return _rechazo(uuid, "FUERA_DE_FECHA")
        if fecha != hoy_lima() and not motivo_cambio:
            return _rechazo(uuid, "MOTIVO_REQUERIDO")
    elif a_lima(marcado).date() != fecha or fecha > hoy_lima():
        return _rechazo(uuid, "FUERA_DE_FECHA")

    if motivo_no_lectivo(fecha, seccion.anio_escolar):
        return _rechazo(uuid, "DIA_NO_LECTIVO")

    if estado not in (None, *reglas.ESTADOS):
        return _rechazo(uuid, "ESTADO_INVALIDO")

    desde_panel = origen == Registro.Origen.PANEL
    with transaction.atomic():
        sesion = obtener_o_crear_sesion(seccion, fecha, bloque, usuario)
        registro = (
            Registro.objects.select_for_update()
            .select_related("justificacion")
            .filter(sesion=sesion, matricula=matricula)
            .first()
        )

        # Regla 2: re-escaneo = duplicado, no cambia nada.
        if registro and metodo == Registro.Metodo.QR:
            return ResultadoMarca(
                uuid, "duplicada", "YA_REGISTRADO",
                f"Ya registrado a las {hora_texto(registro.marcado_en)}", registro, registro.estado,
            )

        if registro:
            gana, codigo = reglas.nueva_marca_gana(
                registro.estado, registro.marcado_en, registro.origen == Registro.Origen.PANEL, marcado, desde_panel
            )
            if not gana:
                return _rechazo(uuid, codigo, registro)

        tiene_justificacion = registro is not None and hasattr(registro, "justificacion")
        if estado == Estado.JUSTIFICADO and not (justificacion and justificacion.get("motivo")) and not tiene_justificacion:
            return _rechazo(uuid, "MOTIVO_REQUERIDO", registro)

        # Quitar la marca (tocar el botón activo).
        if estado is None:
            if registro:
                _historial(None, sesion, matricula, registro.estado, None, usuario, motivo_cambio)
                registro.delete()
            return ResultadoMarca(uuid, "aplicada", estado_final=None)

        anterior = registro.estado if registro else None
        if registro is None:
            registro = Registro(sesion=sesion, matricula=matricula)

        if estado == Estado.JUSTIFICADO:
            if anterior in (Estado.FALTA, Estado.TARDE):
                registro.estado_original = anterior
            elif anterior is None:
                registro.estado_original = Estado.FALTA
        else:
            registro.estado_original = ""
            if tiene_justificacion:
                registro.justificacion.delete()

        registro.estado = estado
        registro.metodo = metodo
        registro.origen = origen
        registro.marcado_en = marcado
        registro.marcado_por = usuario
        registro.dispositivo_id = (dispositivo_id or "")[:64]
        registro.uuid_cliente = uuid
        registro.hora_corregida = corregida
        registro.save()

        if estado == Estado.JUSTIFICADO and justificacion and justificacion.get("motivo"):
            Justificacion.objects.update_or_create(
                registro=registro,
                defaults={
                    "motivo": justificacion["motivo"],
                    "detalle": (justificacion.get("detalle") or "")[:300],
                    "creada_por": usuario,
                },
            )

        if anterior != estado:
            _historial(registro, sesion, matricula, anterior, estado, usuario, motivo_cambio)

    return ResultadoMarca(uuid, "aplicada", registro=registro, estado_final=registro.estado)


# --------------------------------------------------------------------------
# Escaneo QR
# --------------------------------------------------------------------------
def escanear(usuario, *, codigo, modo="PUERTA", seccion_id=None, marcado_en=None, uuid_cliente=None, dispositivo_id=""):
    """Resultado: ok | duplicado | invalido | otra_seccion | rechazado."""
    token = leer_codigo_qr(codigo)
    carnet = None
    if token:
        carnet = Carnet.objects.filter(token_hash=hash_token(token), estado=Carnet.Estado.ACTIVO).select_related(
            "estudiante"
        ).first()
    if carnet is None:
        return {"resultado": "invalido", "mensaje": "Código no válido", "detalle": "Carnet dado de baja o inexistente"}

    anio = AnioEscolar.activo_actual()
    matricula = (
        Matricula.objects.filter(estudiante=carnet.estudiante, anio_escolar=anio, estado=Matricula.Estado.ACTIVA)
        .select_related("seccion__grado__nivel", "seccion__turno", "estudiante")
        .first()
    )
    if matricula is None:
        return {"resultado": "invalido", "mensaje": "Código no válido", "detalle": "El estudiante no tiene matrícula activa"}

    seccion = matricula.seccion
    base = {"estudiante": datos_estudiante(matricula), "seccion": datos_seccion(seccion)}

    if modo == "SECCION":
        destino = Seccion.objects.filter(pk=seccion_id).first()
        if destino is None or not acceso.puede_marcar(usuario, destino, None, "QR"):
            return {**base, "resultado": "rechazado", "mensaje": "No puedes escanear en esta sección"}
        if destino.id != seccion.id:
            return {**base, "resultado": "otra_seccion",
                    "mensaje": f"Pertenece a {seccion.nombre_corto} — no se registró"}
    elif not acceso.puede_marcar(usuario, seccion, None, "QR"):
        return {**base, "resultado": "otra_seccion",
                "mensaje": f"Pertenece a {seccion.nombre_corto} — no está entre tus secciones"}

    ahora = timezone.now()
    marcado, _ = reglas.validar_marcado_en(
        marcado_en, ahora, settings.MARCA_TOLERANCIA_PASADO, settings.MARCA_TOLERANCIA_FUTURO
    )
    local = a_lima(marcado)
    calculado = reglas.estado_por_hora(local.time(), regla_de(seccion.turno))

    res = aplicar_marca(
        usuario, matricula_id=matricula.id, seccion_id=seccion.id, fecha=local.date(),
        estado=calculado.estado, metodo=Registro.Metodo.QR, marcado_en=marcado,
        uuid_cliente=uuid_cliente, dispositivo_id=dispositivo_id,
    )
    contador = Registro.objects.filter(
        sesion__fecha=local.date(), metodo=Registro.Metodo.QR,
        **({"sesion__seccion": seccion} if modo == "SECCION" else {}),
    ).count()
    base["escaneados_hoy"] = contador

    if res.resultado == "duplicada":
        return {**base, "resultado": "duplicado", "estado": res.estado_final,
                "registro_id": res.registro.id if res.registro else None,
                "hora": hora_texto(res.registro.marcado_en) if res.registro else None,
                "marcado_en": res.registro.marcado_en.isoformat() if res.registro else None,
                "fecha": local.date().isoformat(),
                "mensaje": res.detalle or "Ya registrado"}
    if res.resultado == "rechazada":
        return {**base, "resultado": "rechazado", "codigo": res.codigo, "mensaje": res.detalle,
                "estado": res.estado_final}

    estado = res.estado_final
    return {
        **base,
        "resultado": "ok",
        "estado": estado,
        "registro_id": res.registro.id,
        "hora": hora_texto(res.registro.marcado_en),
        "marcado_en": res.registro.marcado_en.isoformat(),
        "fecha": local.date().isoformat(),
        "mensaje": "Presente registrado" if estado == Estado.PRESENTE else "Tarde registrada",
        "advertencia": "Pasó la hora límite: revisa si corresponde falta." if calculado.fuera_de_hora else None,
    }


def datos_estudiante(matricula):
    e = matricula.estudiante
    return {
        "id": e.id,
        "matricula_id": matricula.id,
        "codigo": e.codigo_estudiante,
        "apellidos": e.apellidos,
        "nombres": e.nombres,
        "nombre_completo": e.nombre_completo,
        "iniciales": e.iniciales,
    }


def datos_seccion(seccion):
    return {
        "id": seccion.id,
        "grado": seccion.grado.corto,
        "letra": seccion.letra,
        "nombre_corto": seccion.nombre_corto,
        "nombre": seccion.nombre_largo,
        "nivel": seccion.grado.nivel.get_nombre_display(),
        "turno": seccion.turno.get_nombre_display(),
        "descripcion": f"{seccion.nombre_largo} · {seccion.grado.nivel.get_nombre_display()}",
    }


# --------------------------------------------------------------------------
# Cerrar sesión ("Guardar lista") y cierre automático del día
# --------------------------------------------------------------------------
def cerrar_sesion(usuario, seccion, fecha, bloque=None):
    sesion = obtener_o_crear_sesion(seccion, fecha, bloque, usuario)
    if sesion.estado != SesionAsistencia.EstadoSesion.CERRADA:
        sesion.estado = SesionAsistencia.EstadoSesion.CERRADA
        sesion.cerrada_en = timezone.now()
        sesion.save(update_fields=["estado", "cerrada_en", "actualizado_en"])
    return sesion


def cerrar_dia(fecha: date) -> dict:
    """Regla 4: los sin marcar de las sesiones del día quedan como F y se cierran."""
    config = Configuracion.obtener()
    resumen = {"sesiones": 0, "faltas_creadas": 0, "omitido": None}
    if motivo := motivo_no_lectivo(fecha):
        resumen["omitido"] = motivo
        return resumen

    momento = timezone.make_aware(datetime.combine(fecha, time(23, 59)))
    for sesion in SesionAsistencia.objects.filter(fecha=fecha).select_related("seccion"):
        with transaction.atomic():
            if config.auto_falta_al_cierre:
                marcados = Registro.objects.filter(sesion=sesion).values_list("matricula_id", flat=True)
                faltantes = Matricula.objects.filter(
                    seccion=sesion.seccion, estado=Matricula.Estado.ACTIVA, fecha_alta__lte=fecha
                ).exclude(id__in=list(marcados))
                nuevos = [
                    Registro(
                        sesion=sesion, matricula=m, estado=Estado.FALTA, metodo=Registro.Metodo.AUTO,
                        origen=Registro.Origen.SISTEMA, marcado_en=momento,
                    )
                    for m in faltantes
                ]
                Registro.objects.bulk_create(nuevos)
                resumen["faltas_creadas"] += len(nuevos)
            if sesion.estado != SesionAsistencia.EstadoSesion.CERRADA:
                sesion.estado = SesionAsistencia.EstadoSesion.CERRADA
                sesion.cerrada_en = timezone.now()
                sesion.save(update_fields=["estado", "cerrada_en", "actualizado_en"])
            resumen["sesiones"] += 1
    log.info("cerrar_dia %s: %s", fecha, resumen)
    return resumen


# --------------------------------------------------------------------------
# Justificar
# --------------------------------------------------------------------------
def comprimir_foto(archivo) -> ContentFile:
    """Máx. 1600 px por lado, JPEG calidad 80."""
    imagen = Image.open(archivo)
    imagen = ImageOps.exif_transpose(imagen).convert("RGB")
    imagen.thumbnail((1600, 1600))
    salida = io.BytesIO()
    imagen.save(salida, format="JPEG", quality=80, optimize=True)
    return ContentFile(salida.getvalue())


def puede_editar_registro(usuario, registro) -> bool:
    sesion = registro.sesion
    if not acceso.puede_justificar(usuario, sesion.seccion, sesion.bloque):
        return False
    return usuario.puede("asistencia.editar_fechas_pasadas") or sesion.fecha == hoy_lima()


def justificar(usuario, registro: Registro, *, motivo, detalle="", foto=None, origen=Registro.Origen.APP):
    """Regla 6: convierte F o T en J conservando el estado original."""
    from apps.comun.excepciones import ErrorNegocio

    if not puede_editar_registro(usuario, registro):
        raise ErrorNegocio("No puedes justificar este registro.", "sin_permiso", status_code=403)
    if registro.estado not in (Estado.FALTA, Estado.TARDE, Estado.JUSTIFICADO):
        raise ErrorNegocio("Solo se justifican faltas o tardanzas.", "estado_no_justificable")
    if motivo not in Justificacion.Motivo.values:
        raise ErrorNegocio("Elige un motivo válido.", "motivo_invalido")

    with transaction.atomic():
        anterior = registro.estado
        if anterior != Estado.JUSTIFICADO:
            registro.estado_original = anterior
            registro.estado = Estado.JUSTIFICADO
            registro.origen = origen
            registro.marcado_por = usuario
            registro.save(update_fields=["estado", "estado_original", "origen", "marcado_por", "actualizado_en"])
            _historial(registro, registro.sesion, registro.matricula, anterior, Estado.JUSTIFICADO, usuario, "Justificación")

        just, _ = Justificacion.objects.get_or_create(
            registro=registro, defaults={"motivo": motivo, "creada_por": usuario}
        )
        just.motivo = motivo
        just.detalle = (detalle or "")[:300]
        if foto:
            if just.foto:
                just.foto.delete(save=False)
            just.foto.save(f"registro-{registro.id}.jpg", comprimir_foto(foto), save=False)
        just.save()
    return just
