from django.contrib import admin

from .models import Justificacion, MarcaCliente, Registro, RegistroHistorial, SesionAsistencia


class RegistroInline(admin.TabularInline):
    model = Registro
    extra = 0
    fields = ["matricula", "estado", "metodo", "marcado_en", "marcado_por"]
    readonly_fields = fields
    can_delete = False


@admin.register(SesionAsistencia)
class SesionAsistenciaAdmin(admin.ModelAdmin):
    list_display = ["seccion", "fecha", "bloque", "estado", "abierta_por"]
    list_filter = ["estado", "fecha", "seccion__grado"]
    date_hierarchy = "fecha"
    inlines = [RegistroInline]


@admin.register(Registro)
class RegistroAdmin(admin.ModelAdmin):
    list_display = ["matricula", "sesion", "estado", "metodo", "origen", "marcado_en", "hora_corregida"]
    list_filter = ["estado", "metodo", "origen", "sesion__fecha"]
    search_fields = ["matricula__estudiante__apellido_paterno", "matricula__estudiante__nombres"]
    raw_id_fields = ["sesion", "matricula"]


@admin.register(Justificacion)
class JustificacionAdmin(admin.ModelAdmin):
    list_display = ["registro", "motivo", "estado_revision", "creada_por", "creado_en"]
    list_filter = ["motivo", "estado_revision"]
    raw_id_fields = ["registro"]


@admin.register(RegistroHistorial)
class RegistroHistorialAdmin(admin.ModelAdmin):
    list_display = ["registro", "estado_anterior", "estado_nuevo", "cambiado_por", "cambiado_en", "motivo"]
    raw_id_fields = ["registro", "sesion", "matricula"]


@admin.register(MarcaCliente)
class MarcaClienteAdmin(admin.ModelAdmin):
    list_display = ["uuid_cliente", "usuario", "resultado", "codigo", "recibida_en"]
    list_filter = ["resultado"]
