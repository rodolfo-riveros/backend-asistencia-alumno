from datetime import datetime, timedelta

from django.db import models, transaction

from apps.comun.modelos import ModeloBase


class Institucion(ModeloBase):
    """Registro único con los datos de la I.E."""

    nombre = models.CharField(max_length=150, default="I.E. [Nombre de la institución]")
    nombre_corto = models.CharField(
        max_length=40, blank=True, help_text="Para espacios pequeños (menú, app). Vacío = nombre completo."
    )
    codigo_modular = models.CharField(max_length=20, blank=True)
    ugel = models.CharField(max_length=100, blank=True)
    logo = models.ImageField(upload_to="institucion/", blank=True)
    imagen_portada = models.ImageField(
        upload_to="institucion/", blank=True, help_text="Foto del colegio para las pantallas de ingreso."
    )
    direccion = models.CharField(max_length=200, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    correo = models.EmailField(blank=True)

    class Meta:
        verbose_name = "institución"
        verbose_name_plural = "institución"

    def __str__(self):
        return self.nombre

    @classmethod
    def obtener(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def nombre_visible(self):
        return self.nombre_corto or self.nombre

    @property
    def version_imagenes(self):
        """Cambia al guardar: evita que el navegador o la app muestren un logo viejo."""
        return int(self.actualizado_en.timestamp()) if self.actualizado_en else 0


class AnioEscolar(ModeloBase):
    anio = models.PositiveSmallIntegerField(unique=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    activo = models.BooleanField(default=False)

    class Meta:
        verbose_name = "año escolar"
        verbose_name_plural = "años escolares"
        ordering = ["-anio"]

    def __str__(self):
        return str(self.anio)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.activo:
                AnioEscolar.objects.exclude(pk=self.pk).filter(activo=True).update(activo=False)
            super().save(*args, **kwargs)

    @classmethod
    def activo_actual(cls):
        return cls.objects.filter(activo=True).first()


class Turno(ModeloBase):
    class Nombre(models.TextChoices):
        MANANA = "MANANA", "Mañana"
        TARDE = "TARDE", "Tarde"

    nombre = models.CharField(max_length=10, choices=Nombre.choices, unique=True)
    hora_ingreso = models.TimeField()
    tolerancia_min = models.PositiveSmallIntegerField(default=10)
    hora_limite_falta = models.TimeField(
        null=True, blank=True, help_text="Vacío = hora de ingreso + 120 minutos."
    )

    class Meta:
        verbose_name = "turno"
        verbose_name_plural = "turnos"
        ordering = ["hora_ingreso"]

    def __str__(self):
        return self.get_nombre_display()

    @property
    def limite_falta(self):
        if self.hora_limite_falta:
            return self.hora_limite_falta
        base = datetime.combine(datetime(2000, 1, 1), self.hora_ingreso)
        return (base + timedelta(minutes=120)).time()

    @property
    def tarde_desde(self):
        """Primer minuto que se marca tarde (7:45 + 10 → 7:56)."""
        base = datetime.combine(datetime(2000, 1, 1), self.hora_ingreso)
        return (base + timedelta(minutes=self.tolerancia_min + 1)).time()


class DiaNoLectivo(ModeloBase):
    class Motivo(models.TextChoices):
        FERIADO = "FERIADO", "Feriado nacional"
        ANIVERSARIO = "ANIVERSARIO", "Aniversario de la institución"
        LOCAL = "LOCAL", "Feriado regional o local"
        VACACIONES = "VACACIONES", "Vacaciones"
        OTRO = "OTRO", "Otro día sin clases"

    anio_escolar = models.ForeignKey(AnioEscolar, on_delete=models.PROTECT, related_name="dias_no_lectivos")
    fecha = models.DateField()
    motivo = models.CharField(max_length=12, choices=Motivo.choices, default=Motivo.FERIADO)
    descripcion = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name = "día no lectivo"
        verbose_name_plural = "días no lectivos"
        ordering = ["fecha"]
        constraints = [models.UniqueConstraint(fields=["anio_escolar", "fecha"], name="uniq_dia_no_lectivo")]

    def __str__(self):
        return f"{self.fecha} · {self.descripcion or self.get_motivo_display()}"


class Configuracion(ModeloBase):
    """Registro único con la configuración de asistencia."""

    class ModoAsistencia(models.TextChoices):
        DIARIA = "DIARIA", "Solo diaria (tutor)"
        DIARIA_Y_POR_BLOQUE = "DIARIA_Y_POR_BLOQUE", "Diaria y por bloque de horario"

    modo_asistencia = models.CharField(max_length=20, choices=ModoAsistencia.choices, default=ModoAsistencia.DIARIA)
    auto_falta_al_cierre = models.BooleanField(default=True)
    umbral_faltas = models.PositiveSmallIntegerField(default=3)
    umbral_tardanzas = models.PositiveSmallIntegerField(default=4)

    class Meta:
        verbose_name = "configuración"
        verbose_name_plural = "configuración"

    def __str__(self):
        return "Configuración de asistencia"

    @classmethod
    def obtener(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def permite_bloques(self):
        return self.modo_asistencia == self.ModoAsistencia.DIARIA_Y_POR_BLOQUE
