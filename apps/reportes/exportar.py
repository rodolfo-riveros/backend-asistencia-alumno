"""Exportes a Excel (openpyxl, con los colores del diseño)."""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from apps.asistencia import reglas
from apps.comun.fechas import DIAS_CORTOS, fecha_larga

TINTA = "14213D"
COLORES = {  # estado: (fondo, texto)
    "P": ("E3F1E8", "17603B"),
    "T": ("FBEEDB", "8A4A05"),
    "F": ("B42318", "FFFFFF"),
    "J": ("2453A6", "FFFFFF"),
}
ESTADO_SECCION = {
    "COMPLETA": ("E3F1E8", "17603B", "Completa"),
    "EN_CURSO": ("FBEEDB", "8A4A05", "En curso"),
    "SIN_INICIAR": ("FBE4E1", "9A1F15", "Sin iniciar"),
}
fino = Side(style="thin", color="E4E2DA")
BORDE = Border(left=fino, right=fino, top=fino, bottom=fino)


def _relleno(hex_color):
    return PatternFill("solid", fgColor=hex_color)


def _pct_num(valor):
    """Para Excel: número (0,929) con formato %, así se puede seguir calculando."""
    return float(valor) / 100 if valor is not None else None


def _titulo(hoja, texto, subtitulo, ancho_cols):
    hoja["A1"] = texto
    hoja["A1"].font = Font(bold=True, size=14, color=TINTA)
    hoja["A2"] = subtitulo
    hoja["A2"].font = Font(color="4B5565")
    hoja.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(ancho_cols, 1))


def _encabezado(hoja, fila, columnas):
    for i, texto in enumerate(columnas, start=1):
        c = hoja.cell(row=fila, column=i, value=texto)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = _relleno(TINTA)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BORDE


def _anchos(hoja, anchos):
    for i, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[get_column_letter(i)].width = ancho


def _guardar(libro) -> bytes:
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def excel_dashboard(resumen: dict, institucion: str) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Por sección"
    _titulo(hoja, f"Asistencia del día · {institucion}", fecha_larga(resumen["fecha"], con_anio=True), 9)

    kpis = [
        ("Asistencia general", _pct_num(resumen["porcentaje"]), "0.0%"),
        ("Registrados", resumen["registrados"], None),
        ("Total de estudiantes", resumen["total"], None),
        ("Presentes", resumen["presentes"], None),
        ("Tardes", resumen["tardes"], None),
        ("Faltas", resumen["faltas"], None),
        ("Justificados", resumen["justificados"], None),
        ("Sin registrar", resumen["sin_registrar"], None),
    ]
    for i, (k, v, fmt) in enumerate(kpis):
        hoja.cell(row=4 + i, column=1, value=k).font = Font(bold=True)
        c = hoja.cell(row=4 + i, column=2, value=v)
        if fmt:
            c.number_format = fmt

    fila0 = 4 + len(kpis) + 1
    _encabezado(hoja, fila0, ["Sección", "Tutor(a)", "Registrados", "Total", "P", "T", "F", "J", "Estado"])
    for n, x in enumerate(resumen["secciones"], start=fila0 + 1):
        bg, fg, texto = ESTADO_SECCION[x.estado]
        valores = [
            f"{x.seccion.nombre_corto} · {x.seccion.grado.nivel}",
            x.seccion.tutor.nombre_completo if x.seccion.tutor else "—",
            x.registrados, x.total, x.p, x.t, x.f, x.j, texto,
        ]
        for col, v in enumerate(valores, start=1):
            c = hoja.cell(row=n, column=col, value=v)
            c.border = BORDE
            if col >= 3:
                c.alignment = Alignment(horizontal="center")
        estado = hoja.cell(row=n, column=9)
        estado.fill, estado.font = _relleno(bg), Font(bold=True, color=fg)
    _anchos(hoja, [26, 28, 12, 9, 7, 7, 7, 7, 14])

    g = libro.create_sheet("Por grado")
    _encabezado(g, 1, ["Grado", "% asistencia (P+T+J)", "Registrados"])
    for n, x in enumerate(resumen["por_grado"], start=2):
        g.cell(row=n, column=1, value=f"{x['grado'].nombre} · {x['grado'].nivel}")
        c = g.cell(row=n, column=2, value=_pct_num(x["porcentaje"]))
        c.number_format = "0.0%"
        g.cell(row=n, column=3, value=x["registrados"])
    _anchos(g, [24, 22, 14])
    return _guardar(libro)


def excel_mensual(m: dict, titulo: str, mes_texto: str) -> bytes:
    """Matriz estudiante × días con el color de cada estado (Resumen mensual)."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Resumen mensual"
    n_dias = len(m["dias"])
    _titulo(hoja, f"Resumen mensual · {titulo}", f"{mes_texto} · {len(m['filas'])} estudiantes · {n_dias} días hábiles", n_dias + 6)

    # Leyenda
    for i, (e, nombre) in enumerate([("P", "Presente"), ("T", "Tarde"), ("F", "Falta"), ("J", "Justificado")]):
        c = hoja.cell(row=3, column=1 + i * 2, value=e)
        c.fill, c.font = _relleno(COLORES[e][0]), Font(bold=True, color=COLORES[e][1])
        c.alignment = Alignment(horizontal="center")
        hoja.cell(row=3, column=2 + i * 2, value=nombre)

    fila_enc = 5
    columnas = ["Estudiante"] + [f"{DIAS_CORTOS[d.weekday()][0]}\n{d.day}" for d in m["dias"]] + ["P", "T", "F", "J", "%"]
    _encabezado(hoja, fila_enc, columnas)
    hoja.row_dimensions[fila_enc].height = 30
    for n, x in enumerate(m["filas"], start=fila_enc + 1):
        hoja.cell(row=n, column=1, value=x.nombre).border = BORDE
        for k, estado in enumerate(x.celdas, start=2):
            c = hoja.cell(row=n, column=k, value=estado or "")
            c.alignment = Alignment(horizontal="center")
            c.border = BORDE
            if estado:
                c.fill, c.font = _relleno(COLORES[estado][0]), Font(bold=True, color=COLORES[estado][1])
        base = n_dias + 2
        for k, v in enumerate([x.p, x.t, x.f, x.j]):
            c = hoja.cell(row=n, column=base + k, value=v)
            c.alignment, c.font, c.border = Alignment(horizontal="center"), Font(bold=True), BORDE
        c = hoja.cell(row=n, column=base + 4, value=_pct_num(x.porcentaje))
        c.number_format, c.border = "0.0%", BORDE
        if x.porcentaje is not None and x.porcentaje < 90:
            c.font = Font(bold=True, color="9A1F15")

    pie = fila_enc + len(m["filas"]) + 2
    hoja.cell(row=pie, column=1, value="% = (presente + tarde + justificado) ÷ días hábiles registrados").font = Font(italic=True, color="4B5565")
    if m["promedio"] is not None:
        hoja.cell(row=pie + 1, column=1, value="Promedio de la sección").font = Font(bold=True)
        c = hoja.cell(row=pie + 1, column=2, value=m["promedio"] / 100)
        c.number_format = "0.0%"
    _anchos(hoja, [34] + [4.5] * n_dias + [5, 5, 5, 5, 8])
    hoja.freeze_panes = hoja.cell(row=fila_enc + 1, column=2)
    return _guardar(libro)


def excel_tabla(titulo: str, subtitulo: str, columnas: list[str], filas: list[list], anchos: list[int], pct_cols=()) -> bytes:
    """Tabla simple (% por estudiante, alertas, diario)."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = titulo[:31]
    _titulo(hoja, titulo, subtitulo, len(columnas))
    _encabezado(hoja, 4, columnas)
    for n, valores in enumerate(filas, start=5):
        for col, v in enumerate(valores, start=1):
            c = hoja.cell(row=n, column=col, value=v)
            c.border = BORDE
            if col - 1 in pct_cols:
                c.number_format = "0.0%"
            if isinstance(v, str) and v in COLORES:
                c.fill, c.font = _relleno(COLORES[v][0]), Font(bold=True, color=COLORES[v][1])
                c.alignment = Alignment(horizontal="center")
    _anchos(hoja, anchos)
    hoja.freeze_panes = "A5"
    return _guardar(libro)


def a_pct(valor):
    return _pct_num(valor)


def texto_pct(valor):
    return reglas.formatear_porcentaje(valor)
