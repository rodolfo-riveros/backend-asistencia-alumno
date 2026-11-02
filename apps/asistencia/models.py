from django.conf import settings
from django.db import models

from apps.academico.models import BloqueHorario, Seccion
from apps.comun.modelos import ModeloBase
from apps.estudiantes.models import Matricula


class Estado(models.TextChoices):
    PRESENTE = "P", "Presente"
    TARDE = "T", "Tarde"
    FALTA = "F", "Falta"
    JUSTIFICADO = "J", "Justificado"


class SesionAsistencia(ModeloBase):
    class EstadoSesion(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        CERRADA = "CERRADA", "Cerrada"

    seccion = models.ForeignKey(Seccion, on_delete=models.PROTECT, related_name="sesiones")
    fecha = models.DateField()
    bloque = models.ForeignKey(BloqueHorario, on_delete=models.PROTECT, null=True, blank=True, related_name="sesiones")
    abierta_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    estado = models.CharField(max_length=8, choices=EstadoSesion.choices, default=EstadoSesion.ABIERTA)
    cerrada_en = models.DateTimeField(null=True, blank=True)
    # bloque_id o 0 si es diaria. En MySQL un NULL no choca en un UNIQUE,
    # así que la unicidad (sección, fecha, bloque) se apoya en esta columna.
    bloque_clave = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        verbose_name = "sesión de asistencia"
        verbose_name_plural = "sesiones de asistencia"
        ordering = ["-fecha"]
        constraints = [
            models.UniqueConstraint(fields=["seccion", "fecha", "bloque_clave"], name="uniq_sesion_seccion_fecha_bloque"),
        ]
        indexes = [models.Index(fields=["fecha"], name="idx_sesion_fecha")]

    def __str__(self):
        return f"{self.seccion.nombre_corto} · {self.fecha}"

    def save(self, *args, **kwargs):
        self.bloque_clave = self.bloque_id or 0
        super().save(*args, **kwargs)


class Registro(ModeloBase):
    class Metodo(models.TextChoices):
        QR = "QR", "QR"
        MANUAL = "MANUAL", "Manual"
        AUTO = "AUTO", "Automático"

    class Origen(models.TextChoices):
        APP = "APP", "App móvil"
        PANEL = "PANEL", "Panel"
        SISTEMA = "SISTEMA", "Sistema"

    sesion = models.ForeignKey(SesionAsistencia, on_delete=models.CASCADE, related_name="registros")
    matricula = models.ForeignKey(Matricula, on_delete=models.PROTECT, related_name="registros")
    estado = models.CharField(max_length=1, choices=Estado.choices)
    estado_original = models.CharField(max_length=1, choices=Estado.choices, blank=True)
    metodo = models.CharField(max_length=6, choices=Metodo.choices, default=Metodo.MANUAL)
    origen = models.CharField(max_length=7, choices=Origen.choices, default=Origen.APP)
    marcado_en = models.DateTimeField()
    marcado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    dispositivo_id = models.CharField(max_length=64, blank=True)
    uuid_cliente = models.UUIDField(null=True, blank=True, unique=True)
    hora_corregida = models.BooleanField(default=False)

    class Meta:
        verbose_name = "registro"
        verbose_name_plural = "registros"
        constraints = [models.UniqueConstraint(fields=["sesion", "matricula"], name="uniq_registro_sesion_matricula")]
        indexes = [models.Index(fields=["sesion", "estado"], name="idx_registro_sesion_estado")]

    def __str__(self):
        return f"{self.matricula.estudiante} · {self.sesion.fecha} · {self.estado}"


class Justificacion(ModeloBase):
    class Motivo(models.TextChoices):
        SALUD = "SALUD", "Salud"
        FAMILIAR = "FAMILIAR", "Motivo familiar"
        TRAMITE = "TRAMITE", "Trámite"
        OTRO = "OTRO", "Otro"

    class Revision(models.TextChoices):
        APROBADA = "APROBADA", "Aprobada"
        PENDIENTE = "PENDIENTE", "Pendiente"
        RECHAZADA = "RECHAZADA", "Rechazada"

    registro = models.OneToOneField(Registro, on_delete=models.CASCADE, related_name="justificacion")
    motivo = models.CharField(max_length=10, choices=Motivo.choices)
    detalle = models.CharField(max_length=300, blank=True)
    foto = models.ImageField(upload_to="justificaciones/%Y/%m/", blank=True)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    estado_revision = models.CharField(max_length=10, choices=Revision.choices, default=Revision.APROBADA)

    class Meta:
        verbose_name = "justificación"
        verbose_name_plural = "justificaciones"

    def __str__(self):
        return f"{self.get_motivo_display()} · {self.registro}"


class RegistroHistorial(models.Model):
    """Auditoría: cada cambio de estado de un registro."""

    registro = models.ForeignKey(Registro, on_delete=models.SET_NULL, null=True, related_name="historial")
    sesion = models.ForeignKey(SesionAsistencia, on_delete=models.CASCADE, related_name="+")
    matricula = models.ForeignKey(Matricula, on_delete=models.PROTECT, related_name="+")
    estado_anterior = models.CharField(max_length=1, blank=True)
    estado_nuevo = models.CharField(max_length=1, blank=True, help_text="Vacío = se quitó la marca.")
    cambiado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    motivo = models.CharField(max_length=200, blank=True)
    cambiado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "cambio de registro"
        verbose_name_plural = "historial de registros"
        ordering = ["-cambiado_en"]


class MarcaCliente(models.Model):
    """Bitácora de cada marca recibida desde la app (idempotencia por uuid_cliente)."""

    uuid_cliente = models.UUIDField(unique=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    registro = models.ForeignKey(Registro, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resultado = models.CharField(max_length=10)
    codigo = models.CharField(max_length=40, blank=True)
    recibida_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "marca recibida"
        verbose_name_plural = "marcas recibidas"
