from django.contrib import admin

from .models import AnioEscolar, Configuracion, DiaNoLectivo, Institucion, Turno


@admin.register(Institucion)
class InstitucionAdmin(admin.ModelAdmin):
    list_display = ["nombre", "codigo_modular", "ugel"]


@admin.register(AnioEscolar)
class AnioEscolarAdmin(admin.ModelAdmin):
    list_display = ["anio", "fecha_inicio", "fecha_fin", "activo"]


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "hora_ingreso", "tolerancia_min", "hora_limite_falta"]


@admin.register(DiaNoLectivo)
class DiaNoLectivoAdmin(admin.ModelAdmin):
    list_display = ["fecha", "motivo", "descripcion", "anio_escolar"]
    list_filter = ["anio_escolar", "motivo"]


@admin.register(Configuracion)
class ConfiguracionAdmin(admin.ModelAdmin):
    list_display = ["modo_asistencia", "auto_falta_al_cierre", "umbral_faltas", "umbral_tardanzas"]
