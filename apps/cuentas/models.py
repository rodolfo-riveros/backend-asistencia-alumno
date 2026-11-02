from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone

from apps.comun.modelos import ModeloBase

from .permisos import CODIGOS, ROL_ADMIN


class Rol(ModeloBase):
    """Rol configurable desde el panel. Sus permisos deciden qué ve y hace cada usuario."""

    codigo = models.SlugField("código", max_length=30, unique=True)
    nombre = models.CharField(max_length=60)
    descripcion = models.CharField("descripción", max_length=200, blank=True)
    permisos = models.JSONField(default=list, blank=True)
    es_sistema = models.BooleanField(default=False, help_text="Rol inicial: no se puede eliminar.")

    class Meta:
        verbose_name = "rol"
        verbose_name_plural = "roles"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def es_admin(self):
        return self.codigo == ROL_ADMIN

    def lista_permisos(self) -> set[str]:
        # El administrador siempre tiene todo (así nadie queda fuera del sistema).
        return set(CODIGOS) if self.es_admin else set(self.permisos or [])


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, email, password, **extra):
        if not email:
            raise ValueError("El correo es obligatorio.")
        usuario = self.model(email=self.normalize_email(email).lower(), **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._crear(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("rol_id", ROL_ADMIN)
        return self._crear(email, password, **extra)


class Usuario(AbstractUser):
    username = None
    first_name = None
    last_name = None

    email = models.EmailField("correo", unique=True)
    rol = models.ForeignKey(
        Rol, to_field="codigo", db_column="rol", on_delete=models.PROTECT, related_name="usuarios", default="DOCENTE",
    )
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    celular = models.CharField(max_length=15, blank=True)
    debe_cambiar_password = models.BooleanField(default=False)
    expo_push_token = models.CharField(max_length=200, blank=True)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombres", "apellidos"]

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return f"{self.nombre_completo} ({self.email})"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}".strip()

    @property
    def nombre_corto(self):
        """'Marisol' para el saludo 'Hola, Marisol'."""
        return (self.nombres or "").split(" ")[0]

    @property
    def iniciales(self):
        return f"{(self.nombres or ' ')[0]}{(self.apellidos or ' ')[0]}".strip().upper()

    # --- Permisos (definidos por su rol) ---
    @property
    def permisos(self) -> set[str]:
        if not hasattr(self, "_permisos"):
            self._permisos = set(CODIGOS) if self.is_superuser else self.rol.lista_permisos()
        return self._permisos

    def puede(self, permiso: str) -> bool:
        return self.is_active and permiso in self.permisos

    @property
    def acceso_panel(self) -> bool:
        return any(p.startswith("panel.") for p in self.permisos) and self.is_active

    # --- Bloqueo por intentos fallidos ---
    def esta_bloqueado(self):
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > timezone.now())

    def registrar_fallo(self):
        self.intentos_fallidos += 1
        if self.intentos_fallidos >= settings.LOGIN_MAX_INTENTOS:
            self.bloqueado_hasta = timezone.now() + timedelta(minutes=settings.LOGIN_BLOQUEO_MINUTOS)
            self.intentos_fallidos = 0
        self.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])

    def registrar_exito(self):
        if self.intentos_fallidos or self.bloqueado_hasta:
            self.intentos_fallidos = 0
            self.bloqueado_hasta = None
            self.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
