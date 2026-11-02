from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    ordering = ["apellidos", "nombres"]
    list_display = ["email", "nombres", "apellidos", "rol", "is_active", "debe_cambiar_password"]
    list_filter = ["rol", "is_active"]
    search_fields = ["email", "nombres", "apellidos"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos", {"fields": ("nombres", "apellidos", "celular", "rol", "debe_cambiar_password")}),
        ("Seguridad", {"fields": ("intentos_fallidos", "bloqueado_hasta", "expo_push_token")}),
        ("Permisos", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "nombres", "apellidos", "rol", "password1", "password2"),
        }),
    )
