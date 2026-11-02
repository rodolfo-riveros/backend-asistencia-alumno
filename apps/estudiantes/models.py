import hashlib
import secrets

from django.db import models, transaction

from apps.academico.models import Seccion
from apps.comun.modelos import ModeloBase
from apps.institucion.models import AnioEscolar

PREFIJO_QR = "AE1."


class Estudiante(ModeloBase):
    class Sexo(models.TextChoices):
        M = "M", "Masculino"
        F = "F", "Femenino"

    codigo_estudiante = models.CharField(max_length=20, unique=True)
    dni = models.CharField(max_length=12, unique=True, null=True, blank=True)
    apellido_paterno = models.CharField(max_length=60)
    apellido_materno = models.CharField(max_length=60, blank=True)
    nombres = models.CharField(max_length=100)
    sexo = models.CharField(max_length=1, choices=Sexo.choices, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "estudiante"
        verbose_name_plural = "estudiantes"
        ordering = ["apellido_paterno", "apellido_materno", "nombres"]

    def __str__(self):
        return f"{self.apellidos}, {self.nombres}"

    def save(self, *args, **kwargs):
        self.dni = (self.dni or "").strip() or None
        super().save(*args, **kwargs)

    @property
    def apellidos(self):
        return f"{self.apellido_paterno} {self.apellido_materno}".strip()

    @property
    def nombre_completo(self):
        """'Flores Cusi, Mateo Joaquín'."""
        return f"{self.apellidos}, {self.nombres}"

    @property
    def iniciales(self):
        return f"{self.apellido_paterno[:1]}{self.nombres[:1]}".upper()


class Apoderado(ModeloBase):
    estudiante = models.ForeignKey(Estudiante, on_delete=models.CASCADE, related_name="apoderados")
    nombre = models.CharField(max_length=150)
    parentesco = models.CharField(max_length=30, blank=True)
    celular = models.CharField(max_length=15, blank=True)
    es_principal = models.BooleanField(default=True)

    class Meta:
        verbose_name = "apoderado"
        verbose_name_plural = "apoderados"
        ordering = ["-es_principal", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.parentesco})"


class Matricula(ModeloBase):
    class Estado(models.TextChoices):
        ACTIVA = "ACTIVA", "Activa"
        RETIRADO = "RETIRADO", "Retirado"
        TRASLADADO = "TRASLADADO", "Trasladado"

    estudiante = models.ForeignKey(Estudiante, on_delete=models.PROTECT, related_name="matriculas")
    seccion = models.ForeignKey(Seccion, on_delete=models.PROTECT, related_name="matriculas")
    anio_escolar = models.ForeignKey(AnioEscolar, on_delete=models.PROTECT, related_name="matriculas")
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVA)
    fecha_alta = models.DateField()
    fecha_baja = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "matrícula"
        verbose_name_plural = "matrículas"
        constraints = [
            models.UniqueConstraint(fields=["estudiante", "anio_escolar"], name="uniq_matricula_estudiante_anio")
        ]
        indexes = [models.Index(fields=["seccion", "estado"], name="idx_matricula_seccion_estado")]

    def __str__(self):
        return f"{self.estudiante} · {self.seccion.nombre_corto}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def leer_codigo_qr(codigo: str) -> str | None:
    """Devuelve el token de 'AE1.<token>' o None si el formato no es válido."""
    codigo = (codigo or "").strip()
    if not codigo.startswith(PREFIJO_QR):
        return None
    token = codigo[len(PREFIJO_QR):]
    return token if 16 <= len(token) <= 64 else None


class Carnet(ModeloBase):
    class Estado(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        REVOCADO = "REVOCADO", "Revocado"
        BAJA = "BAJA", "Dado de baja"

    estudiante = models.ForeignKey(Estudiante, on_delete=models.CASCADE, related_name="carnets")
    token = models.CharField(max_length=64, unique=True)
    token_hash = models.CharField(max_length=64, unique=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVO)
    emitido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "carnet"
        verbose_name_plural = "carnets"
        ordering = ["-emitido_en"]

    def __str__(self):
        return f"Carnet {self.estudiante} · {self.get_estado_display()}"

    @property
    def contenido_qr(self):
        """Lo único que va dentro del QR: 'AE1.<token>' (sin datos personales)."""
        return f"{PREFIJO_QR}{self.token}"

    @classmethod
    def emitir(cls, estudiante):
        """Crea un carnet nuevo y revoca los anteriores activos."""
        with transaction.atomic():
            cls.objects.filter(estudiante=estudiante, estado=cls.Estado.ACTIVO).update(estado=cls.Estado.REVOCADO)
            token = secrets.token_urlsafe(16)
            return cls.objects.create(estudiante=estudiante, token=token, token_hash=hash_token(token))

    @classmethod
    def dar_de_baja(cls, estudiante):
        return cls.objects.filter(estudiante=estudiante, estado=cls.Estado.ACTIVO).update(estado=cls.Estado.BAJA)
