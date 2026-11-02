"""Importación de estudiantes desde Excel (plantilla propia o nómina de SIAGIE).

Flujo: leer_excel() → vista previa con errores por fila → importar() en una transacción.
Las columnas se reconocen por el nombre del encabezado (sin tildes ni mayúsculas).
"""

import io
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from apps.academico.models import Seccion
from apps.comun.fechas import hoy_lima, sin_tildes
from apps.estudiantes.models import Apoderado, Estudiante
from apps.estudiantes.servicios import matricular

COLUMNAS = [
    "codigo_estudiante", "dni", "apellido_paterno", "apellido_materno", "nombres", "sexo", "fecha_nacimiento",
    "grado", "seccion", "apoderado_nombre", "apoderado_parentesco", "apoderado_celular",
]
OBLIGATORIAS = ["codigo_estudiante", "apellido_paterno", "nombres", "grado", "seccion"]
MAX_FILAS = 2000

# Encabezados alternativos (SIAGIE y variantes comunes), ya normalizados.
ALIAS = {
    "codigo_estudiante": ["codigo estudiante", "codigo del estudiante", "codigo de estudiante", "codigo", "cod estudiante",
                          "codigo siagie", "cod"],
    "dni": ["dni", "documento", "nro documento", "numero de documento", "n documento", "num documento",
            "documento de identidad", "dni estudiante", "nro de documento"],
    "apellido_paterno": ["apellido paterno", "ap paterno", "paterno", "primer apellido"],
    "apellido_materno": ["apellido materno", "ap materno", "materno", "segundo apellido"],
    "nombres": ["nombres", "nombre", "nombres del estudiante", "nombre del estudiante"],
    "sexo": ["sexo", "genero"],
    "fecha_nacimiento": ["fecha nacimiento", "fecha de nacimiento", "f nacimiento", "fec nac", "fecha nac", "nacimiento"],
    "grado": ["grado"],
    "seccion": ["seccion"],
    "apoderado_nombre": ["apoderado nombre", "apoderado", "nombre apoderado", "nombre del apoderado", "nombres apoderado",
                         "apellidos y nombres del apoderado"],
    "apoderado_parentesco": ["apoderado parentesco", "parentesco", "parentesco apoderado"],
    "apoderado_celular": ["apoderado celular", "celular", "celular apoderado", "celular del apoderado", "telefono",
                          "telefono apoderado"],
}
ORDINALES = {"primer": 1, "segund": 2, "tercer": 3, "cuart": 4, "quint": 5, "sext": 6}


def normalizar(texto) -> str:
    t = sin_tildes(str(texto or "")).replace("n°", "n").replace("nº", "n")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


MAPA_ENCABEZADOS = {alias: col for col, alias_list in ALIAS.items() for alias in [col.replace("_", " "), *alias_list]}


@dataclass
class Fila:
    numero: int
    datos: dict
    errores: list = field(default_factory=list)
    accion: str = ""
    seccion_id: int | None = None
    seccion_texto: str = ""

    @property
    def valida(self):
        return not self.errores


@dataclass
class Resultado:
    filas: list
    errores_generales: list
    columnas_encontradas: list

    @property
    def validas(self):
        return [f for f in self.filas if f.valida]

    @property
    def invalidas(self):
        return [f for f in self.filas if not f.valida]


# ------------------------------------------------------------------ lectura
def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def _buscar_encabezado(hoja):
    mejor = (None, {})
    for idx, fila in enumerate(hoja.iter_rows(min_row=1, max_row=15, values_only=True), start=1):
        mapa = {}
        for col, valor in enumerate(fila):
            clave = MAPA_ENCABEZADOS.get(normalizar(valor))
            if clave and clave not in mapa:
                mapa[clave] = col
        if len(mapa) > len(mejor[1]):
            mejor = (idx, mapa)
    return mejor


def leer_excel(archivo, anio) -> Resultado:
    try:
        libro = load_workbook(archivo, read_only=True, data_only=True)
    except Exception:
        return Resultado([], ["No se pudo leer el archivo. Verifica que sea un Excel .xlsx válido."], [])
    hoja = libro.worksheets[0]
    fila_enc, mapa = _buscar_encabezado(hoja)
    faltan = [c for c in OBLIGATORIAS if c not in mapa]
    if fila_enc is None or faltan:
        return Resultado([], [
            "No se encontraron las columnas obligatorias: " + ", ".join(faltan or OBLIGATORIAS)
            + ". Descarga la plantilla para ver el formato."
        ], list(mapa))

    filas = []
    for numero, valores in enumerate(hoja.iter_rows(min_row=fila_enc + 1, values_only=True), start=fila_enc + 1):
        datos = {c: (valores[i] if i < len(valores) else None) for c, i in mapa.items()}
        if all(_texto(v) == "" for v in datos.values()):
            continue
        filas.append(Fila(numero=numero, datos=datos))
        if len(filas) > MAX_FILAS:
            return Resultado([], [f"El archivo tiene más de {MAX_FILAS} filas. Divídelo en partes."], list(mapa))
    libro.close()
    if not filas:
        return Resultado([], ["El archivo no tiene filas de estudiantes debajo del encabezado."], list(mapa))
    validar(filas, anio)
    return Resultado(filas, [], list(mapa))


# ------------------------------------------------------------------ validación
def _grado(valor) -> int | None:
    t = normalizar(valor)
    if m := re.search(r"[1-6]", t):
        return int(m.group())
    for raiz, n in ORDINALES.items():
        if t.startswith(raiz):
            return n
    return None


def _fecha(valor):
    if valor in (None, ""):
        return None, None
    if isinstance(valor, datetime):
        return valor.date(), None
    if isinstance(valor, date):
        return valor, None
    t = _texto(valor)
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(t, formato).date(), None
        except ValueError:
            continue
    return None, f"Fecha de nacimiento inválida «{t}» (usa dd/mm/aaaa)"


def _sexo(valor):
    t = normalizar(valor)
    if not t:
        return "", None
    if t in ("m", "h", "masculino", "hombre", "varon"):
        return "M", None
    if t in ("f", "femenino", "mujer"):
        return "F", None
    return "", f"Sexo inválido «{_texto(valor)}» (usa M o F)"


def validar(filas, anio):
    secciones = {
        (s.grado.numero, s.letra.upper()): s
        for s in Seccion.objects.filter(anio_escolar=anio, grado__nivel__activo=True).select_related("grado", "grado__nivel")
    }
    codigos_bd = set(Estudiante.objects.values_list("codigo_estudiante", flat=True))
    dni_bd = dict(Estudiante.objects.exclude(dni__isnull=True).values_list("dni", "codigo_estudiante"))
    vistos_codigo, vistos_dni = {}, {}
    hoy = hoy_lima()

    for f in filas:
        d, err = f.datos, f.errores
        limpio = {c: _texto(d.get(c)) for c in COLUMNAS}

        for c in OBLIGATORIAS:
            if not limpio[c]:
                err.append(f"Falta {c.replace('_', ' ')}")

        codigo = limpio["codigo_estudiante"]
        if codigo:
            if len(codigo) > 20:
                err.append("Código demasiado largo (máx. 20)")
            if codigo in vistos_codigo:
                err.append(f"Código repetido en la fila {vistos_codigo[codigo]}")
            vistos_codigo.setdefault(codigo, f.numero)

        dni = limpio["dni"]
        if dni:
            if dni.isdigit() and len(dni) in (6, 7):  # Excel quita los ceros iniciales
                dni = dni.zfill(8)
            if not (dni.isdigit() and len(dni) == 8):
                err.append(f"DNI inválido «{limpio['dni']}» (8 dígitos)")
            elif dni in vistos_dni:
                err.append(f"DNI repetido en la fila {vistos_dni[dni]}")
            elif dni in dni_bd and dni_bd[dni] != codigo:
                err.append(f"El DNI ya pertenece al estudiante con código {dni_bd[dni]}")
            vistos_dni.setdefault(dni, f.numero)
        limpio["dni"] = dni

        sexo, e = _sexo(d.get("sexo"))
        limpio["sexo"] = sexo
        if e:
            err.append(e)

        fecha, e = _fecha(d.get("fecha_nacimiento"))
        if e:
            err.append(e)
        elif fecha and not (date(hoy.year - 20, 1, 1) <= fecha <= hoy):
            err.append(f"Fecha de nacimiento fuera de rango ({fecha:%d/%m/%Y})")
        limpio["fecha_nacimiento"] = fecha.isoformat() if fecha else ""

        if limpio["grado"] and limpio["seccion"]:
            numero = _grado(limpio["grado"])
            letra = limpio["seccion"].upper()[:2]
            seccion = secciones.get((numero, letra)) if numero else None
            if seccion is None:
                err.append(f"No existe la sección {limpio['grado']} «{limpio['seccion']}» en {anio}")
            else:
                f.seccion_id, f.seccion_texto = seccion.id, seccion.nombre_corto

        cel = re.sub(r"\D", "", limpio["apoderado_celular"])
        if cel and not (len(cel) == 9 and cel.startswith("9")):
            err.append(f"Celular inválido «{limpio['apoderado_celular']}» (9 dígitos)")
        limpio["apoderado_celular"] = cel

        for c, maximo in (("apellido_paterno", 60), ("apellido_materno", 60), ("nombres", 100), ("apoderado_nombre", 150)):
            if len(limpio[c]) > maximo:
                err.append(f"{c.replace('_', ' ').capitalize()} demasiado largo")
        for c in ("apellido_paterno", "apellido_materno", "nombres", "apoderado_nombre"):
            limpio[c] = " ".join(limpio[c].split()).title() if limpio[c].isupper() or limpio[c].islower() else limpio[c]

        f.datos = limpio
        f.accion = "Actualizar" if codigo in codigos_bd else "Nuevo"


# ------------------------------------------------------------------ importación
def serializar(filas) -> list[dict]:
    return [asdict(f) for f in filas if f.valida]


def importar(filas: list[dict], anio) -> dict:
    """Importa filas ya validadas (de la sesión) en una sola transacción."""
    resumen = {"nuevos": 0, "actualizados": 0}
    secciones = {s.id: s for s in Seccion.objects.filter(anio_escolar=anio)}
    with transaction.atomic():
        for f in filas:
            d = f["datos"]
            est = Estudiante.objects.filter(codigo_estudiante=d["codigo_estudiante"]).first()
            nuevo = est is None
            est = est or Estudiante(codigo_estudiante=d["codigo_estudiante"])
            est.apellido_paterno = d["apellido_paterno"]
            est.apellido_materno = d["apellido_materno"]
            est.nombres = d["nombres"]
            if d["dni"]:
                est.dni = d["dni"]
            if d["sexo"]:
                est.sexo = d["sexo"]
            if d["fecha_nacimiento"]:
                est.fecha_nacimiento = date.fromisoformat(d["fecha_nacimiento"])
            est.save()
            matricular(est, secciones[f["seccion_id"]], anio)

            if d["apoderado_nombre"]:
                apo = est.apoderados.filter(es_principal=True).first() or Apoderado(estudiante=est, es_principal=True)
                apo.nombre = d["apoderado_nombre"]
                apo.parentesco = d["apoderado_parentesco"][:30]
                apo.celular = d["apoderado_celular"] or apo.celular
                apo.save()
            resumen["nuevos" if nuevo else "actualizados"] += 1
    return resumen


# ------------------------------------------------------------------ plantilla
def plantilla_xlsx() -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Estudiantes"
    hoja.append(COLUMNAS)
    hoja.append(["20260000001", "71234567", "Flores", "Cusi", "Mateo Joaquín", "M", "14/05/2018", "3", "B",
                 "Rosa Cusi Mamani", "Madre", "987654321"])
    hoja.append(["20260000002", "", "Apaza", "Huamán", "Luciana Valeria", "F", "02/11/2018", "3", "B", "", "", ""])
    relleno = PatternFill("solid", fgColor="14213D")
    for celda in hoja[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = relleno
        celda.alignment = Alignment(horizontal="center")
    for col, ancho in zip("ABCDEFGHIJKL", (16, 11, 18, 18, 22, 7, 16, 7, 9, 24, 14, 14)):
        hoja.column_dimensions[col].width = ancho
    # Códigos y DNI como texto para no perder ceros a la izquierda.
    for col in ("A", "B", "L"):
        for fila in range(2, 1001):
            hoja[f"{col}{fila}"].number_format = "@"
    hoja.freeze_panes = "A2"

    ayuda = libro.create_sheet("Instrucciones")
    for linea in [
        ["Cómo llenar la plantilla"],
        [""],
        ["Obligatorias: codigo_estudiante, apellido_paterno, nombres, grado, seccion."],
        ["grado: número del 1 al 6 (también acepta «3.º», «Tercero»). seccion: letra (A, B…)."],
        ["La sección debe existir en el año activo (créala en «Grados y secciones»)."],
        ["dni (opcional): 8 dígitos. sexo: M o F. fecha_nacimiento: dd/mm/aaaa."],
        ["apoderado_celular: 9 dígitos, empieza con 9."],
        ["Si el código ya existe, se actualizan sus datos y su matrícula."],
        ["También puedes subir la nómina exportada de SIAGIE: las columnas se reconocen por su nombre."],
    ]:
        ayuda.append(linea)
    ayuda["A1"].font = Font(bold=True, size=14)
    ayuda.column_dimensions["A"].width = 100

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()
