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


def poner_clave_inicial(usuario) -> str | None:
    """Con DNI, la contraseña es el DNI (fácil de recordar). Sin DNI, una temporal que debe cambiar.

    Devuelve la clave temporal para mostrarla una vez, o None si se usó el DNI.
    """
    usuario.intentos_fallidos, usuario.bloqueado_hasta = 0, None
    if usuario.dni:
        usuario.set_password(usuario.dni)
        usuario.debe_cambiar_password = False
        return None
    clave = generar_password_temporal()
    usuario.set_password(clave)
    usuario.debe_cambiar_password = True
    return clave


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
    tutor_dicta_todo = forms.BooleanField(
        required=False, initial=True, label="El tutor(a) dicta todos los cursos",
        help_text="Lo usual en primaria. Los cursos de otros docentes (p. ej. Inglés) se asignan aparte y no se tocan.",
    )

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
    dni_obligatorio = True

    class Meta:
        model = Usuario
        fields = ["nombres", "apellidos", "dni", "email", "celular", "rol", "is_active"]
        labels = {"email": "Correo", "is_active": "Cuenta activa", "rol": "Rol"}
        widgets = {"dni": forms.TextInput(attrs={"inputmode": "numeric", "maxlength": 8, "autocomplete": "off"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dni"].required = self.dni_obligatorio
        self.fields["dni"].error_messages["required"] = "Ingresa su DNI: será su contraseña."
        self.fields["dni"].help_text = "Será su contraseña para entrar a la app y al panel."
        self.fields["email"].help_text = "Con este correo inicia sesión."
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

    def clean_dni(self):
        dni = (self.cleaned_data.get("dni") or "").strip()
        if not dni:
            return None
        if not (dni.isdigit() and len(dni) == 8):
            raise ValidationError("El DNI tiene 8 dígitos.")
        if Usuario.objects.filter(dni=dni).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe un usuario con este DNI.")
        return dni

    def save(self, commit=True):
        u = super().save(commit=False)
        anterior = self.initial.get("dni")
        # Si cambia el DNI y aún usaba el anterior como contraseña, la contraseña pasa al DNI nuevo
        if u.pk and u.dni and anterior and anterior != u.dni and u.check_password(anterior):
            u.set_password(u.dni)
        if commit:
            u.save()
        return u


class UsuarioForm(DocenteForm):
    dni_obligatorio = False

    class Meta(DocenteForm.Meta):
        fields = ["nombres", "apellidos", "dni", "email", "rol", "celular", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dni"].help_text = "Opcional. Si lo pones, será su contraseña; si no, se genera una temporal."
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
    todos_cursos = forms.BooleanField(required=False, initial=True, label="Dicta todos los cursos de la sección")

    def __init__(self, *args, anio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["seccion"].queryset = Seccion.objects.filter(anio_escolar=anio).select_related("grado", "turno")


class BloqueForm(forms.Form):
    """Un curso en uno o varios días a la misma hora. El docente por defecto es el tutor."""

    curso = forms.ModelChoiceField(queryset=Curso.objects.filter(activo=True), label="Curso / área", empty_label="Elige el curso")
    docente = NombreDocenteChoice(queryset=Usuario.objects.none(), required=False, label="Lo dicta")
    dias = forms.TypedMultipleChoiceField(choices=DIAS_SEMANA, coerce=int, label="Días", widget=forms.CheckboxSelectMultiple)
    hora_inicio = forms.TimeField(label="Inicio", widget=HORA)
    hora_fin = forms.TimeField(label="Fin", widget=HORA)

    def __init__(self, *args, seccion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.seccion = seccion
        self.fields["docente"].queryset = docentes()
        tutor = seccion.tutor if seccion else None
        self.fields["docente"].empty_label = f"Su tutor(a): {tutor.nombre_completo}" if tutor else "Elige quién lo dicta"
        self.fields["docente"].help_text = "Cambia solo si lo dicta otro docente (p. ej. Inglés o Educación Física)."

    def clean(self):
        datos = super().clean()
        inicio, fin = datos.get("hora_inicio"), datos.get("hora_fin")
        if inicio and fin and fin <= inicio:
            self.add_error("hora_fin", "Debe ser posterior a la hora de inicio.")
        curso = datos.get("curso")
        if curso and not datos.get("docente"):
            actual = Asignacion.objects.filter(seccion=self.seccion, curso=curso).select_related("docente").first()
            datos["docente"] = actual.docente if actual else self.seccion.tutor
            if not datos["docente"]:
                self.add_error("docente", "La sección no tiene tutor: elige quién dicta el curso.")
        return datos


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
    desde = forms.DateField(label="Fecha", widget=FECHA)
    hasta = forms.DateField(label="Hasta", widget=FECHA, required=False, help_text="Solo si son varios días seguidos, como vacaciones.")
    motivo = forms.ChoiceField(
        choices=[c for c in DiaNoLectivo.Motivo.choices if c[0] != DiaNoLectivo.Motivo.FERIADO], label="Motivo",
        initial=DiaNoLectivo.Motivo.ANIVERSARIO, widget=forms.RadioSelect,
    )
    descripcion = forms.CharField(
        label="Descripción", max_length=150, required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ej.: 45.º aniversario de la I.E., Vacaciones de medio año"}),
    )

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


class NuevoAnioForm(forms.Form):
    COPIAR = [
        ("todo", "Todo"),
        ("secciones", "Solo grados y secciones"),
        ("nada", "Empezar vacío"),
    ]
    CUANDO = [
        ("despues", "Lo preparo ahora y lo activo cuando empiecen las clases"),
        ("ahora", "Empezar a usarlo desde hoy"),
    ]

    anio = forms.IntegerField(label="Año", min_value=2000, max_value=2100)
    fecha_inicio = forms.DateField(label="Primer día de clases", widget=FECHA)
    fecha_fin = forms.DateField(label="Último día de clases", widget=FECHA)
    copiar_de = forms.ModelChoiceField(
        queryset=AnioEscolar.objects.order_by("-anio"), required=False, label="Copiar desde", empty_label=None,
    )
    copiar = forms.ChoiceField(choices=COPIAR, initial="todo", widget=forms.RadioSelect, label="¿Qué traemos del año anterior?")
    cuando = forms.ChoiceField(choices=CUANDO, initial="despues", widget=forms.RadioSelect, label="¿Cuándo se usa?")

    def clean_anio(self):
        anio = self.cleaned_data["anio"]
        if AnioEscolar.objects.filter(anio=anio).exists():
            raise ValidationError(f"El año {anio} ya existe.")
        return anio

    def clean(self):
        d = super().clean()
        ini, fin, anio = d.get("fecha_inicio"), d.get("fecha_fin"), d.get("anio")
        if ini and fin and fin <= ini:
            self.add_error("fecha_fin", "Debe ser posterior al primer día de clases.")
        if ini and anio and ini.year != anio:
            self.add_error("fecha_inicio", f"Debe ser una fecha de {anio}.")
        if fin and anio and fin.year != anio:
            self.add_error("fecha_fin", f"Debe ser una fecha de {anio}.")
        copiar = d.get("copiar")
        if copiar == "nada" or not d.get("copiar_de"):
            d["copiar_de"] = None
        d["copiar_secciones"] = copiar in ("todo", "secciones")
        d["copiar_cursos"] = copiar == "todo"
        d["activar"] = d.get("cuando") == "ahora"
        return d


class AnioFechasForm(forms.ModelForm):
    """Solo las fechas: activar un año es una acción aparte (y explícita)."""

    class Meta:
        model = AnioEscolar
        fields = ["fecha_inicio", "fecha_fin"]
        labels = {"fecha_inicio": "Inicio de clases", "fecha_fin": "Fin de clases"}
        widgets = {"fecha_inicio": FECHA, "fecha_fin": FECHA}

    def clean(self):
        d = super().clean()
        if d.get("fecha_inicio") and d.get("fecha_fin") and d["fecha_fin"] <= d["fecha_inicio"]:
            raise ValidationError("La fecha de fin debe ser posterior al inicio.")
        return d
