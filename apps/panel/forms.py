import secrets
import string

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.academico.models import Asignacion, BloqueHorario, Curso, Grado, Seccion
from apps.cuentas.models import Rol, Usuario
from apps.cuentas.permisos import PERMISOS, roles_con
from apps.estudiantes.models import Apoderado, Estudiante, Matricula
from apps.institucion.models import AnioEscolar, Configuracion, DiaNoLectivo, Institucion, Turno

DIAS_SEMANA = [(1, "Lunes"), (2, "Martes"), (3, "Miércoles"), (4, "Jueves"), (5, "Viernes")]
FECHA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
HORA = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")


def generar_password_temporal() -> str:
    """10 caracteres sin letras ambiguas (0/O, 1/l)."""
    alfabeto = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    return "".join(secrets.choice(alfabeto) for _ in range(10))


def docentes(activos=True):
    """Usuarios cuyo rol tiene el permiso 'Es docente'."""
    qs = Usuario.objects.filter(rol__in=roles_con("academico.docente")).select_related("rol")
    return qs.filter(is_active=True).order_by("apellidos", "nombres") if activos else qs


def roles_docentes():
    return Rol.objects.filter(codigo__in=roles_con("academico.docente")).order_by("nombre")


class NombreDocenteChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.apellidos}, {obj.nombres}"


class SeccionChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.nombre_largo} · {obj.turno}"


# --------------------------------------------------------------------- sesión
class LoginForm(forms.Form):
    email = forms.EmailField(label="Correo", widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}))
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class CambiarPasswordForm(forms.Form):
    nueva = forms.CharField(label="Nueva contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                            help_text="Mínimo 8 caracteres, no solo números.")
    repetir = forms.CharField(label="Repite la contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean(self):
        datos = super().clean()
        if datos.get("nueva") and datos.get("nueva") != datos.get("repetir"):
            raise ValidationError("Las contraseñas no coinciden.")
        if datos.get("nueva"):
            validate_password(datos["nueva"], self.usuario)
        return datos


# --------------------------------------------------------------------- académico
class SeccionForm(forms.ModelForm):
    tutor = NombreDocenteChoice(queryset=Usuario.objects.none(), required=False, label="Tutor(a)")

    class Meta:
        model = Seccion
        fields = ["grado", "letra", "turno", "tutor", "aula", "capacidad"]
        labels = {"letra": "Sección (letra)", "aula": "Aula"}

    def __init__(self, *args, anio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.anio = anio
        self.fields["grado"].queryset = Grado.objects.filter(nivel__activo=True).select_related("nivel")
        self.fields["tutor"].queryset = docentes()

    def clean_letra(self):
        return self.cleaned_data["letra"].strip().upper()

    def clean(self):
        datos = super().clean()
        grado, letra = datos.get("grado"), datos.get("letra")
        if grado and letra and Seccion.objects.filter(anio_escolar=self.anio, grado=grado, letra=letra).exclude(
            pk=self.instance.pk
        ).exists():
            raise ValidationError(f"Ya existe {grado.nombre} · Sección {letra} en {self.anio}.")
        return datos

    def save(self, commit=True):
        self.instance.anio_escolar = self.anio
        return super().save(commit)


class CursoForm(forms.ModelForm):
    class Meta:
        model = Curso
        fields = ["nombre", "activo"]
        labels = {"activo": "Activo"}


class DocenteForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ["nombres", "apellidos", "email", "celular", "rol", "is_active"]
        labels = {"email": "Correo institucional", "is_active": "Cuenta activa", "rol": "Rol"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "rol" in self.fields:
            self.fields["rol"].queryset = roles_docentes()
            self.fields["rol"].empty_label = None
            self.fields["rol"].required = False
            self.fields["rol"].help_text = "Roles con el permiso «Es docente». Se configuran en Usuarios y roles."

    def clean_rol(self):
        rol = self.cleaned_data.get("rol")
        if rol:
            return rol
        if self.instance.pk:
            return self.instance.rol
        return Rol.objects.filter(codigo="DOCENTE").first() or roles_docentes().first()

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if Usuario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe un usuario con este correo.")
        return email


class UsuarioForm(DocenteForm):
    class Meta(DocenteForm.Meta):
        fields = ["nombres", "apellidos", "email", "rol", "celular", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rol"].queryset = Rol.objects.order_by("nombre")
        self.fields["rol"].required = True
        self.fields["rol"].empty_label = "Elige un rol"
        self.fields["rol"].help_text = "Define qué puede hacer en el panel y en la app."

    def clean_rol(self):
        return self.cleaned_data["rol"]


class RolForm(forms.ModelForm):
    permisos = forms.MultipleChoiceField(
        choices=[(c, n) for c, _, n, _ in PERMISOS], required=False, widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Rol
        fields = ["nombre", "descripcion", "permisos"]
        labels = {"nombre": "Nombre del rol", "descripcion": "Descripción"}
        help_texts = {"nombre": "Ej.: Subdirector(a), Secretaria, Coordinador(a) de TOE"}

    def clean_nombre(self):
        nombre = " ".join(self.cleaned_data["nombre"].split())
        if Rol.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe un rol con ese nombre.")
        return nombre

    def save(self, commit=True):
        rol = super().save(commit=False)
        if not rol.pk:
            base = slugify(rol.nombre).upper().replace("-", "_")[:24] or "ROL"
            codigo, n = base, 2
            while Rol.objects.filter(codigo=codigo).exists():
                codigo, n = f"{base}_{n}", n + 1
            rol.codigo = codigo
        rol.permisos = [] if rol.es_admin else self.cleaned_data["permisos"]
        if commit:
            rol.save()
        return rol


class AsignacionForm(forms.Form):
    seccion = SeccionChoice(queryset=Seccion.objects.none(), label="Sección")
    curso = forms.ModelChoiceField(queryset=Curso.objects.filter(activo=True), label="Curso / área")

    def __init__(self, *args, docente=None, anio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.docente = docente
        self.fields["seccion"].queryset = Seccion.objects.filter(anio_escolar=anio).select_related("grado", "turno")

    def clean(self):
        datos = super().clean()
        actual = Asignacion.objects.filter(seccion=datos.get("seccion"), curso=datos.get("curso")).select_related("docente").first()
        if actual:
            quien = "este docente" if actual.docente_id == self.docente.id else actual.docente.nombre_completo
            raise ValidationError(f"{datos['curso']} en {datos['seccion'].nombre_corto} ya está asignado a {quien}.")
        return datos


class TutoriaForm(forms.Form):
    seccion = SeccionChoice(queryset=Seccion.objects.none(), label="Sección")

    def __init__(self, *args, anio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["seccion"].queryset = Seccion.objects.filter(anio_escolar=anio).select_related("grado", "turno")


class BloqueForm(forms.ModelForm):
    dia_semana = forms.TypedChoiceField(choices=DIAS_SEMANA, coerce=int, label="Día")

    class Meta:
        model = BloqueHorario
        fields = ["asignacion", "dia_semana", "hora_inicio", "hora_fin"]
        labels = {"asignacion": "Curso y docente", "hora_inicio": "Inicio", "hora_fin": "Fin"}
        widgets = {"hora_inicio": HORA, "hora_fin": HORA}

    def __init__(self, *args, seccion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.seccion = seccion
        self.fields["asignacion"].queryset = Asignacion.objects.filter(seccion=seccion).select_related("curso", "docente")
        self.fields["asignacion"].label_from_instance = lambda a: f"{a.curso} · {a.docente.nombre_completo}"


# --------------------------------------------------------------------- estudiantes
class EstudianteForm(forms.ModelForm):
    seccion = SeccionChoice(queryset=Seccion.objects.none(), label="Sección (matrícula del año activo)", required=False)

    class Meta:
        model = Estudiante
        fields = ["codigo_estudiante", "dni", "apellido_paterno", "apellido_materno", "nombres", "sexo", "fecha_nacimiento"]
        labels = {"codigo_estudiante": "Código del estudiante", "dni": "DNI", "fecha_nacimiento": "Fecha de nacimiento"}
        widgets = {"fecha_nacimiento": FECHA}

    def __init__(self, *args, anio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.anio = anio
        self.fields["seccion"].queryset = Seccion.objects.filter(anio_escolar=anio).select_related("grado", "turno")
        if self.instance.pk and anio:
            m = Matricula.objects.filter(estudiante=self.instance, anio_escolar=anio).first()
            if m:
                self.fields["seccion"].initial = m.seccion_id

    def clean_dni(self):
        dni = (self.cleaned_data.get("dni") or "").strip()
        if dni and (not dni.isdigit() or len(dni) != 8):
            raise ValidationError("El DNI debe tener 8 dígitos.")
        if dni and Estudiante.objects.filter(dni=dni).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Otro estudiante ya tiene este DNI.")
        return dni or None


class ApoderadoForm(forms.ModelForm):
    class Meta:
        model = Apoderado
        fields = ["nombre", "parentesco", "celular", "es_principal"]
        labels = {"nombre": "Nombre completo", "es_principal": "Contacto principal"}

    def clean_celular(self):
        cel = (self.cleaned_data.get("celular") or "").replace(" ", "")
        if cel and (not cel.isdigit() or len(cel) != 9):
            raise ValidationError("El celular debe tener 9 dígitos.")
        return cel


class BajaMatriculaForm(forms.Form):
    estado = forms.ChoiceField(
        choices=[(Matricula.Estado.RETIRADO, "Retirado"), (Matricula.Estado.TRASLADADO, "Trasladado")], label="Motivo"
    )
    fecha_baja = forms.DateField(label="Fecha de baja", widget=FECHA)


class ImportarForm(forms.Form):
    archivo = forms.FileField(label="Archivo Excel (.xlsx)", help_text="Plantilla de este panel o nómina exportada de SIAGIE.")

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if not archivo.name.lower().endswith((".xlsx", ".xlsm")):
            raise ValidationError("Sube un archivo .xlsx (Excel). Si tienes .xls, ábrelo y guárdalo como .xlsx.")
        if archivo.size > 5 * 1024 * 1024:
            raise ValidationError("El archivo pesa más de 5 MB.")
        return archivo


# --------------------------------------------------------------------- configuración
class InstitucionForm(forms.ModelForm):
    quitar_logo = forms.BooleanField(required=False, label="Quitar el logo actual")
    quitar_portada = forms.BooleanField(required=False, label="Quitar la portada actual")

    class Meta:
        model = Institucion
        fields = ["nombre", "nombre_corto", "codigo_modular", "ugel", "direccion", "telefono", "correo", "logo", "imagen_portada"]
        labels = {
            "nombre": "Nombre de la I.E.", "nombre_corto": "Nombre corto", "codigo_modular": "Código modular",
            "ugel": "UGEL", "direccion": "Dirección", "telefono": "Teléfono", "correo": "Correo",
            "logo": "Logo", "imagen_portada": "Imagen de portada",
        }
        help_texts = {
            "nombre": "Aparece en la app, el panel, los carnets y los reportes. Ej.: I.E. N.º 50001 San Martín",
            "logo": "PNG o JPG cuadrado. Se muestra en el panel, la app, los carnets y los reportes.",
            "imagen_portada": "Foto horizontal del colegio. Aparece en las pantallas de ingreso.",
        }
        widgets = {
            "logo": forms.FileInput(attrs={"accept": "image/*"}),
            "imagen_portada": forms.FileInput(attrs={"accept": "image/*"}),
        }

    def save(self, commit=True):
        inst = super().save(commit=False)
        if self.cleaned_data.get("quitar_logo") and not self.files.get("logo"):
            inst.logo.delete(save=False)
        if self.cleaned_data.get("quitar_portada") and not self.files.get("imagen_portada"):
            inst.imagen_portada.delete(save=False)
        if commit:
            inst.save()
        return inst

    def clean(self):
        datos = super().clean()
        for campo in ("logo", "imagen_portada"):
            archivo = datos.get(campo)
            if archivo and hasattr(archivo, "size") and archivo.size > 3 * 1024 * 1024:
                self.add_error(campo, "La imagen pesa más de 3 MB.")
        return datos


class GradoForm(forms.ModelForm):
    class Meta:
        model = Grado
        fields = ["nivel", "numero", "nombre", "orden"]
        labels = {"numero": "Número", "nombre": "Nombre", "orden": "Orden en listas"}
        help_texts = {"nombre": "Ej.: 3.º grado, 1.º año, 4 años"}

    def clean(self):
        datos = super().clean()
        if datos.get("nivel") and datos.get("numero") is not None and Grado.objects.filter(
            nivel=datos["nivel"], numero=datos["numero"]
        ).exclude(pk=self.instance.pk).exists():
            raise ValidationError(f"Ya existe el grado {datos['numero']} en {datos['nivel']}.")
        return datos


class ConfiguracionForm(forms.ModelForm):
    class Meta:
        model = Configuracion
        fields = ["modo_asistencia", "auto_falta_al_cierre", "umbral_faltas", "umbral_tardanzas"]
        labels = {
            "modo_asistencia": "Modo de asistencia",
            "auto_falta_al_cierre": "Marcar falta a los sin registrar al cierre del día (23:59)",
            "umbral_faltas": "Alerta de riesgo: faltas en el mes",
            "umbral_tardanzas": "Alerta de riesgo: tardanzas en el mes",
        }


class TurnoForm(forms.ModelForm):
    class Meta:
        model = Turno
        fields = ["hora_ingreso", "tolerancia_min", "hora_limite_falta"]
        labels = {"hora_ingreso": "Hora de ingreso", "tolerancia_min": "Tolerancia (min)", "hora_limite_falta": "Hora límite para falta"}
        help_texts = {"hora_limite_falta": "Vacío = ingreso + 2 horas."}
        widgets = {"hora_ingreso": HORA, "hora_limite_falta": HORA}


class AnioEscolarForm(forms.ModelForm):
    class Meta:
        model = AnioEscolar
        fields = ["anio", "fecha_inicio", "fecha_fin", "activo"]
        labels = {"anio": "Año", "fecha_inicio": "Inicio de clases", "fecha_fin": "Fin de clases", "activo": "Año activo"}
        widgets = {"fecha_inicio": FECHA, "fecha_fin": FECHA}

    def clean(self):
        datos = super().clean()
        if datos.get("fecha_inicio") and datos.get("fecha_fin") and datos["fecha_fin"] <= datos["fecha_inicio"]:
            raise ValidationError("La fecha de fin debe ser posterior al inicio.")
        return datos


class DiaNoLectivoForm(forms.Form):
    desde = forms.DateField(label="Fecha (o desde)", widget=FECHA)
    hasta = forms.DateField(label="Hasta", widget=FECHA, required=False, help_text="Solo para rangos como vacaciones.")
    motivo = forms.ChoiceField(choices=DiaNoLectivo.Motivo.choices, label="Motivo")
    descripcion = forms.CharField(label="Descripción", max_length=150, required=False)

    def __init__(self, *args, anio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.anio = anio

    def clean(self):
        datos = super().clean()
        desde, hasta = datos.get("desde"), datos.get("hasta") or datos.get("desde")
        if desde and hasta:
            if hasta < desde:
                raise ValidationError("«Hasta» debe ser igual o posterior a «desde».")
            if (hasta - desde).days > 120:
                raise ValidationError("El rango no puede superar 120 días.")
            if self.anio and not (self.anio.fecha_inicio.year <= desde.year <= self.anio.fecha_fin.year):
                raise ValidationError(f"La fecha debe pertenecer al año escolar {self.anio}.")
        datos["hasta"] = hasta
        return datos
