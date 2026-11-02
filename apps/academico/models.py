from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.comun.modelos import ModeloBase
from apps.institucion.models import AnioEscolar, Turno


def limitar_a_docentes():
    """Solo usuarios cuyo rol tenga el permiso 'Es docente'."""
    from apps.cuentas.permisos import roles_con

    return {"rol__in": roles_con("academico.docente"), "is_active": True}


class Nivel(ModeloBase):
    class Nombre(models.TextChoices):
        INICIAL = "INICIAL", "Inicial"
        PRIMARIA = "PRIMARIA", "Primaria"
        SECUNDARIA = "SECUNDARIA", "Secundaria"

    nombre = models.CharField(max_length=12, choices=Nombre.choices, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "nivel"
        verbose_name_plural = "niveles"

    def __str__(self):
        return self.get_nombre_display()


class Grado(ModeloBase):
    nivel = models.ForeignKey(Nivel, on_delete=models.PROTECT, related_name="grados")
    numero = models.PositiveSmallIntegerField()
    nombre = models.CharField(max_length=30, help_text="Ej.: 3.º grado")
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "grado"
        verbose_name_plural = "grados"
        ordering = ["orden", "numero"]
        constraints = [models.UniqueConstraint(fields=["nivel", "numero"], name="uniq_grado_nivel")]

    def __str__(self):
        return f"{self.nombre} · {self.nivel}"

    @property
    def corto(self):
        return f"{self.numero}.º"


class Seccion(ModeloBase):
    anio_escolar = models.ForeignKey(AnioEscolar, on_delete=models.PROTECT, related_name="secciones")
    grado = models.ForeignKey(Grado, on_delete=models.PROTECT, related_name="secciones")
    letra = models.CharField(max_length=2)
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name="secciones")
    tutor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tutorias",
        limit_choices_to=limitar_a_docentes,
    )
    aula = models.CharField(max_length=30, blank=True)
    capacidad = models.PositiveSmallIntegerField(default=30)

    class Meta:
        verbose_name = "sección"
        verbose_name_plural = "secciones"
        ordering = ["grado__orden", "grado__numero", "letra"]
        constraints = [
            models.UniqueConstraint(fields=["anio_escolar", "grado", "letra"], name="uniq_seccion_anio_grado_letra")
        ]

    def __str__(self):
        return f"{self.nombre_corto} · {self.anio_escolar}"

    @property
    def nombre_corto(self):
        """'3.º B'."""
        return f"{self.grado.corto} {self.letra}"

    @property
    def nombre_largo(self):
        """'3.º grado · Sección B'."""
        return f"{self.grado.nombre} · Sección {self.letra}"


class Curso(ModeloBase):
    nombre = models.CharField(max_length=60, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Asignacion(ModeloBase):
    seccion = models.ForeignKey(Seccion, on_delete=models.PROTECT, related_name="asignaciones")
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT, related_name="asignaciones")
    docente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="asignaciones",
        limit_choices_to=limitar_a_docentes,
    )

    class Meta:
        verbose_name = "asignación"
        verbose_name_plural = "asignaciones"
        constraints = [models.UniqueConstraint(fields=["seccion", "curso"], name="uniq_asignacion_seccion_curso")]

    def __str__(self):
        return f"{self.curso} · {self.seccion.nombre_corto} · {self.docente.nombre_completo}"


class BloqueHorario(ModeloBase):
    seccion = models.ForeignKey(Seccion, on_delete=models.PROTECT, related_name="bloques")
    asignacion = models.ForeignKey(Asignacion, on_delete=models.PROTECT, related_name="bloques")
    dia_semana = models.PositiveSmallIntegerField(help_text="1 = lunes … 5 = viernes")
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        verbose_name = "bloque de horario"
        verbose_name_plural = "bloques de horario"
        ordering = ["dia_semana", "hora_inicio"]

    def __str__(self):
        return f"{self.asignacion.curso} · {self.seccion.nombre_corto} · {self.dia_semana} {self.hora_inicio:%H:%M}"

    def clean(self):
        if not 1 <= self.dia_semana <= 5:
            raise ValidationError({"dia_semana": "Debe estar entre 1 (lunes) y 5 (viernes)."})
        if self.hora_fin <= self.hora_inicio:
            raise ValidationError({"hora_fin": "Debe ser posterior a la hora de inicio."})
        if self.asignacion_id and self.asignacion.seccion_id != self.seccion_id:
            raise ValidationError({"asignacion": "La asignación pertenece a otra sección."})
        if self.asignacion_id:
            choque = (
                BloqueHorario.objects.filter(
                    asignacion__docente_id=self.asignacion.docente_id,
                    dia_semana=self.dia_semana,
                    hora_inicio__lt=self.hora_fin,
                    hora_fin__gt=self.hora_inicio,
                )
                .exclude(pk=self.pk)
                .first()
            )
            if choque:
                raise ValidationError(f"Choque de horario: el docente ya tiene {choque}.")
        if self.seccion_id:
            ocupado = (
                BloqueHorario.objects.filter(
                    seccion_id=self.seccion_id, dia_semana=self.dia_semana,
                    hora_inicio__lt=self.hora_fin, hora_fin__gt=self.hora_inicio,
                )
                .exclude(pk=self.pk)
                .select_related("asignacion__curso")
                .first()
            )
            if ocupado:
                raise ValidationError(f"Ese horario ya está ocupado: {ocupado}.")
