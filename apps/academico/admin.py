from django.contrib import admin

from .models import Asignacion, BloqueHorario, Curso, Grado, Nivel, Seccion


@admin.register(Nivel)
class NivelAdmin(admin.ModelAdmin):
    list_display = ["nombre", "activo"]


@admin.register(Grado)
class GradoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "nivel", "numero", "orden"]
    list_filter = ["nivel"]


class AsignacionInline(admin.TabularInline):
    model = Asignacion
    extra = 0


@admin.register(Seccion)
class SeccionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "turno", "tutor", "aula", "capacidad"]
    list_filter = ["anio_escolar", "turno", "grado"]
    inlines = [AsignacionInline]


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "activo"]


@admin.register(Asignacion)
class AsignacionAdmin(admin.ModelAdmin):
    list_display = ["seccion", "curso", "docente"]
    list_filter = ["curso", "seccion__grado"]


@admin.register(BloqueHorario)
class BloqueHorarioAdmin(admin.ModelAdmin):
    list_display = ["seccion", "asignacion", "dia_semana", "hora_inicio", "hora_fin"]
    list_filter = ["dia_semana", "seccion__grado"]
