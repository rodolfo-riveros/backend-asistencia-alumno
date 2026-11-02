"""python manage.py sembrar_demo [--reset] [--password Demo2026!]

Crea una I.E. de primaria de ejemplo con docentes, ~25 alumnos por sección,
carnets QR, feriados de Perú 2026 y 20 días hábiles de asistencia.
"""

import random
from datetime import date, datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.academico.models import Asignacion, BloqueHorario, Curso, Grado, Nivel, Seccion
from apps.asistencia.models import (
    Estado, Justificacion, MarcaCliente, Registro, RegistroHistorial, SesionAsistencia,
)
from apps.asistencia.reglas import dias_habiles
from apps.comun.fechas import hoy_lima
from apps.cuentas.models import Usuario
from apps.estudiantes.models import Apoderado, Carnet, Estudiante, Matricula
from apps.institucion.models import AnioEscolar, Configuracion, DiaNoLectivo, Institucion, Turno

PASSWORD_DEMO = "Demo2026!"

DOCENTES = [  # (grado, nombres, apellidos, correo)
    (1, "Rosa", "Huamán Ccori", "r.huaman@ie-ejemplo.edu.pe"),
    (2, "Julio", "Cusi Mamani", "j.cusi@ie-ejemplo.edu.pe"),
    (3, "Marisol", "Quispe Condori", "m.quispe@ie-ejemplo.edu.pe"),
    (4, "Edwin", "Mamani Ttito", "e.mamani@ie-ejemplo.edu.pe"),
    (5, "Karina", "Torres Apaza", "k.torres@ie-ejemplo.edu.pe"),
    (6, "Luis", "Ccori Huallpa", "l.ccori@ie-ejemplo.edu.pe"),
]

CURSOS = [
    "Matemática", "Comunicación", "Personal Social", "Ciencia y Tecnología", "Arte y Cultura",
    "Educación Física", "Educación Religiosa", "Inglés", "Tutoría",
]

# 3.º B usa los alumnos del diseño (03 · Pase de lista / Reporte mensual).
ALUMNOS_DISENO = [
    ("Apaza", "Huamán", "Luciana Valeria", "F"),
    ("Ccahuana", "Quispe", "Diego Alonso", "M"),
    ("Condori", "Mamani", "Ximena Rosa", "F"),
    ("Flores", "Cusi", "Mateo Joaquín", "M"),
    ("Gutiérrez", "Layme", "Adriana Sofía", "F"),
    ("Huillca", "Ttito", "Santiago André", "M"),
    ("Mendoza", "Choque", "Camila Fernanda", "F"),
    ("Puma", "Sullca", "Thiago Gabriel", "M"),
    ("Quispe", "Yupanqui", "Valentina Inés", "F"),
    ("Rojas", "Ccori", "Fabián", "M"),
    ("Sánchez", "Pumayalli", "Antonella", "F"),
    ("Ttito", "Huanca", "Joaquín", "M"),
]

APELLIDOS = [
    "Quispe", "Mamani", "Flores", "Huamán", "Condori", "Ccori", "Cusi", "Choque", "Ttito", "Huallpa",
    "Apaza", "Gutiérrez", "Rojas", "Vargas", "Cárdenas", "Torres", "Ramos", "Chávez", "Mendoza", "Salazar",
    "Paucar", "Puma", "Yupanqui", "Layme", "Sullca", "Huillca", "Ccahuana", "Pumayalli", "Castillo", "Aguilar",
    "Bustamante", "Ccasa", "Pacheco", "Zúñiga", "Champi", "Huaraca", "Sairitupac", "Ancco",
]
NOMBRES_M = [
    "Mateo", "Thiago", "Sebastián", "Santiago", "Diego", "Adriano", "Gael", "Dylan", "Fabricio", "Liam",
    "Alessandro", "Joaquín", "Gabriel", "André", "Benjamín", "Leonardo", "Rodrigo", "Josué", "Iker", "Emiliano",
]
NOMBRES_F = [
    "Valentina", "Camila", "Luciana", "Ximena", "Nayeli", "Kiara", "Mía", "Danna", "Zoe", "Abigail",
    "Antonella", "Adriana", "Sofía", "Fernanda", "Rosa", "Inés", "Alessia", "Brianna", "Micaela", "Ariana",
]
PARENTESCOS = [("Madre", "F"), ("Padre", "M"), ("Madre", "F"), ("Abuela", "F"), ("Tía", "F"), ("Padre", "M")]

FERIADOS_2026 = [
    (date(2026, 1, 1), "Año Nuevo"),
    (date(2026, 4, 2), "Jueves Santo"),
    (date(2026, 4, 3), "Viernes Santo"),
    (date(2026, 5, 1), "Día del Trabajo"),
    (date(2026, 6, 7), "Batalla de Arica y Día de la Bandera"),
    (date(2026, 6, 29), "San Pedro y San Pablo"),
    (date(2026, 7, 23), "Día de la Fuerza Aérea del Perú"),
    (date(2026, 7, 28), "Fiestas Patrias"),
    (date(2026, 7, 29), "Fiestas Patrias"),
    (date(2026, 8, 6), "Batalla de Junín"),
    (date(2026, 8, 30), "Santa Rosa de Lima"),
    (date(2026, 10, 8), "Combate de Angamos"),
    (date(2026, 11, 1), "Todos los Santos"),
    (date(2026, 12, 8), "Inmaculada Concepción"),
    (date(2026, 12, 9), "Batalla de Ayacucho"),
    (date(2026, 12, 25), "Navidad"),
]
VACACIONES_MEDIO_ANIO = (date(2026, 7, 27), date(2026, 8, 7))


class Command(BaseCommand):
    help = "Crea datos de demostración (primaria, año 2026)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Borra los datos académicos y de asistencia antes.")
        parser.add_argument("--password", default=PASSWORD_DEMO, help="Contraseña para todos los usuarios demo.")
        parser.add_argument("--dias", type=int, default=20, help="Días hábiles de asistencia a generar.")
        parser.add_argument("--semilla", type=int, default=2026)

    def handle(self, *args, **opts):
        if Seccion.objects.exists() and not opts["reset"]:
            raise CommandError("Ya hay datos. Usa --reset para borrarlos y volver a sembrar.")
        self.rnd = random.Random(opts["semilla"])
        with transaction.atomic():
            if opts["reset"]:
                self._borrar()
            self._sembrar(opts["password"], opts["dias"])
        self.stdout.write(self.style.SUCCESS("Datos demo creados. Usuarios y contraseña: ver README.md."))

    # ------------------------------------------------------------------
    def _borrar(self):
        for modelo in (
            MarcaCliente, RegistroHistorial, Justificacion, Registro, SesionAsistencia, Carnet, Apoderado,
            Matricula, Estudiante, BloqueHorario, Asignacion, Seccion, Curso, Grado, Nivel, DiaNoLectivo,
            AnioEscolar, Turno,
        ):
            modelo.objects.all().delete()
        Usuario.objects.filter(is_superuser=False).delete()

    def _usuario(self, email, nombres, apellidos, rol, password, **extra):
        u = Usuario.objects.filter(email=email).first() or Usuario(email=email)
        u.nombres, u.apellidos, u.rol_id = nombres, apellidos, rol
        for k, v in extra.items():
            setattr(u, k, v)
        u.set_password(password)
        u.save()
        return u

    def _sembrar(self, password, n_dias):
        inst = Institucion.obtener()
        inst.nombre = "I.E. [Nombre de la institución]"
        inst.codigo_modular = "0000000"
        inst.ugel = "UGEL de ejemplo"
        inst.save()
        Configuracion.obtener()

        anio = AnioEscolar.objects.create(
            anio=2026, fecha_inicio=date(2026, 3, 16), fecha_fin=date(2026, 12, 18), activo=True
        )
        manana = Turno.objects.create(nombre=Turno.Nombre.MANANA, hora_ingreso=time(7, 45), tolerancia_min=10)
        tarde = Turno.objects.create(nombre=Turno.Nombre.TARDE, hora_ingreso=time(12, 45), tolerancia_min=10)

        DiaNoLectivo.objects.bulk_create(
            [DiaNoLectivo(anio_escolar=anio, fecha=f, motivo="FERIADO", descripcion=d) for f, d in FERIADOS_2026]
        )
        feriados = {f for f, _ in FERIADOS_2026}
        d = VACACIONES_MEDIO_ANIO[0]
        vacaciones = []
        while d <= VACACIONES_MEDIO_ANIO[1]:
            if d.weekday() < 5 and d not in feriados:
                vacaciones.append(DiaNoLectivo(anio_escolar=anio, fecha=d, motivo="VACACIONES",
                                               descripcion="Vacaciones de medio año"))
            d += timedelta(days=1)
        DiaNoLectivo.objects.bulk_create(vacaciones)

        primaria = Nivel.objects.create(nombre=Nivel.Nombre.PRIMARIA, activo=True)
        grados = {
            n: Grado.objects.create(nivel=primaria, numero=n, nombre=f"{n}.º grado", orden=n) for n in range(1, 7)
        }
        cursos = [Curso.objects.create(nombre=c) for c in CURSOS]

        self._usuario("admin@demo.edu.pe", "Admin", "Sistema", "ADMIN", password,
                      is_staff=True, is_superuser=True)
        self._usuario("director@demo.edu.pe", "Carlos", "Paucar Rojas", "DIRECTOR", password, is_staff=True)
        self._usuario("auxiliar@demo.edu.pe", "Nancy", "Choque Vargas", "AUXILIAR", password)

        secciones = []
        for numero, nombres, apellidos, email in DOCENTES:
            docente = self._usuario(email, nombres, apellidos, "DOCENTE", password,
                                    celular=f"9{self.rnd.randint(10000000, 99999999)}")
            for letra in ("A", "B"):
                turno = tarde if (numero >= 5 and letra == "B") else manana
                s = Seccion.objects.create(
                    anio_escolar=anio, grado=grados[numero], letra=letra, turno=turno, tutor=docente,
                    aula=f"Aula {numero}{letra}", capacidad=30,
                )
                Asignacion.objects.bulk_create([Asignacion(seccion=s, curso=c, docente=docente) for c in cursos])
                secciones.append(s)

        # Estudiantes, apoderados, matrículas y carnets.
        correlativo = 1
        usados = set()
        matriculas = []
        for s in secciones:
            filas = list(ALUMNOS_DISENO) if (s.grado.numero == 3 and s.letra == "B") else []
            objetivo = 27 if filas else self.rnd.randint(24, 28)
            while len(filas) < objetivo:
                sexo = self.rnd.choice("MF")
                lista = NOMBRES_M if sexo == "M" else NOMBRES_F
                nombres = " ".join(self.rnd.sample(lista, 2)) if self.rnd.random() < 0.6 else self.rnd.choice(lista)
                fila = (self.rnd.choice(APELLIDOS), self.rnd.choice(APELLIDOS), nombres, sexo)
                if fila[:3] not in usados:
                    filas.append(fila)
                usados.add(fila[:3])
            for ap, am, nom, sexo in filas:
                est = Estudiante.objects.create(
                    codigo_estudiante=f"2026{correlativo:06d}",
                    dni=f"{self.rnd.randint(60000000, 79999999)}" if self.rnd.random() < 0.8 else None,
                    apellido_paterno=ap, apellido_materno=am, nombres=nom, sexo=sexo,
                    fecha_nacimiento=date(2026 - 5 - s.grado.numero, self.rnd.randint(1, 12), self.rnd.randint(1, 28)),
                )
                correlativo += 1
                parentesco, genero = self.rnd.choice(PARENTESCOS)
                nombre_apoderado = self.rnd.choice(NOMBRES_F if genero == "F" else NOMBRES_M)
                apellido_apoderado = am if parentesco == "Madre" else ap
                Apoderado.objects.create(
                    estudiante=est, nombre=f"{nombre_apoderado} {apellido_apoderado}",
                    parentesco=parentesco, celular=f"9{self.rnd.randint(10000000, 99999999)}",
                )
                Carnet.emitir(est)
                matriculas.append(Matricula.objects.create(
                    estudiante=est, seccion=s, anio_escolar=anio, fecha_alta=anio.fecha_inicio
                ))

        self._asistencia(anio, secciones, matriculas, n_dias, feriados | {v.fecha for v in vacaciones})
        self.stdout.write(f"  {len(secciones)} secciones · {len(matriculas)} estudiantes")

    def _asistencia(self, anio, secciones, matriculas, n_dias, no_lectivos):
        hoy = hoy_lima()
        fin = min(hoy - timedelta(days=1), anio.fecha_fin)
        habiles = dias_habiles(anio.fecha_inicio, fin, no_lectivos)[-n_dias:]
        por_seccion = {}
        for m in matriculas:
            por_seccion.setdefault(m.seccion_id, []).append(m)

        # Algunos alumnos con más faltas/tardanzas para que aparezcan alertas de riesgo.
        riesgo = {m.id: self.rnd.choice(["F", "T"]) for m in self.rnd.sample(matriculas, k=max(3, len(matriculas) // 25))}
        tz = timezone.get_current_timezone()
        registros, justificaciones = [], []
        for dia in habiles:
            for s in secciones:
                sesion = SesionAsistencia.objects.create(
                    seccion=s, fecha=dia, abierta_por=s.tutor, estado="CERRADA",
                    cerrada_en=datetime.combine(dia, time(9, 0), tzinfo=tz),
                )
                ingreso = datetime.combine(dia, s.turno.hora_ingreso, tzinfo=tz)
                for m in por_seccion[s.id]:
                    r = self.rnd.random()
                    if riesgo.get(m.id) == "F":
                        estado = "F" if r < 0.18 else "P"
                    elif riesgo.get(m.id) == "T":
                        estado = "T" if r < 0.28 else "P"
                    else:
                        estado = "P" if r < 0.875 else "T" if r < 0.925 else "F" if r < 0.975 else "J"
                    if estado == "P":
                        marcado = ingreso - timedelta(minutes=self.rnd.randint(0, 15)) + timedelta(minutes=self.rnd.randint(0, 10))
                    elif estado == "T":
                        marcado = ingreso + timedelta(minutes=self.rnd.randint(11, 40))
                    else:
                        marcado = ingreso + timedelta(minutes=self.rnd.randint(20, 60))
                    registros.append(Registro(
                        sesion=sesion, matricula=m, estado=estado,
                        estado_original="F" if estado == "J" else "",
                        metodo="QR" if estado in "PT" and self.rnd.random() < 0.7 else "MANUAL",
                        marcado_en=marcado, marcado_por=s.tutor,
                    ))
        Registro.objects.bulk_create(registros, batch_size=1000)
        for reg in Registro.objects.filter(estado=Estado.JUSTIFICADO).select_related("sesion__seccion"):
            justificaciones.append(Justificacion(
                registro=reg, motivo=self.rnd.choice(["SALUD", "SALUD", "FAMILIAR", "TRAMITE"]),
                detalle="", creada_por=reg.sesion.seccion.tutor,
            ))
        Justificacion.objects.bulk_create(justificaciones)
        self.stdout.write(f"  {len(habiles)} días hábiles · {len(registros)} registros de asistencia")
