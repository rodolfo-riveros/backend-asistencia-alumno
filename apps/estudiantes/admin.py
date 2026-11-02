from django.contrib import admin, messages

from .models import Apoderado, Carnet, Estudiante, Matricula


class ApoderadoInline(admin.TabularInline):
    model = Apoderado
    extra = 0


class MatriculaInline(admin.TabularInline):
    model = Matricula
    extra = 0


class CarnetInline(admin.TabularInline):
    model = Carnet
    extra = 0
    fields = ["estado", "emitido_en", "token_hash"]
    readonly_fields = ["estado", "emitido_en", "token_hash"]
    can_delete = False


@admin.register(Estudiante)
class EstudianteAdmin(admin.ModelAdmin):
    list_display = ["codigo_estudiante", "apellido_paterno", "apellido_materno", "nombres", "activo"]
    search_fields = ["codigo_estudiante", "dni", "apellido_paterno", "apellido_materno", "nombres"]
    list_filter = ["activo", "matriculas__seccion__grado"]
    inlines = [ApoderadoInline, MatriculaInline, CarnetInline]
    actions = ["regenerar_carnet"]

    @admin.action(description="Regenerar carnet QR (invalida el anterior)")
    def regenerar_carnet(self, request, queryset):
        for estudiante in queryset:
            Carnet.emitir(estudiante)
        self.message_user(request, f"Se regeneraron {queryset.count()} carnets.", messages.SUCCESS)


@admin.register(Matricula)
class MatriculaAdmin(admin.ModelAdmin):
    list_display = ["estudiante", "seccion", "anio_escolar", "estado"]
    list_filter = ["anio_escolar", "estado", "seccion__grado"]
    search_fields = ["estudiante__apellido_paterno", "estudiante__nombres"]


@admin.register(Carnet)
class CarnetAdmin(admin.ModelAdmin):
    list_display = ["estudiante", "estado", "emitido_en"]
    list_filter = ["estado"]
    search_fields = ["estudiante__apellido_paterno", "estudiante__nombres"]
    readonly_fields = ["token", "token_hash", "emitido_en"]
