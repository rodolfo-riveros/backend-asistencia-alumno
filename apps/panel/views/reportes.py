"""Panel · Reportes (docs/diseno/panel-02-reporte-mensual.html)."""

from django.views import View

from apps.academico.models import Grado, Seccion
from apps.comun.fechas import DIAS_CORTOS, fecha_larga, hora_texto, hoy_lima, mes_texto
from apps.institucion.models import AnioEscolar
from apps.reportes import agregados
from apps.reportes.exportar import a_pct, excel_mensual, excel_tabla

from ..mixins import PanelMixin
from .dashboard import XLSX, leer_fecha, pdf_o_impresion, respuesta_archivo

PESTANAS = [
    ("diario", "Diario por sección"),
    ("mensual", "Resumen mensual"),
    ("estudiantes", "% por estudiante"),
    ("alertas", "Alertas de riesgo"),
]


def meses_del_anio(anio, hoy):
    """[('2026-03', 'Marzo 2026'), …] hasta el mes actual."""
    meses = []
    a, m = anio.fecha_inicio.year, anio.fecha_inicio.month
    fin = min(anio.fecha_fin, hoy)
    while (a, m) <= (fin.year, fin.month):
        meses.append((f"{a:04d}-{m:02d}", mes_texto(a, m)))
        a, m = (a, m + 1) if m < 12 else (a + 1, 1)
    return list(reversed(meses))


class ReportesView(PanelMixin, View):
    menu = "reportes"
    permiso = "panel.reportes"

    def get(self, request):
        hoy = hoy_lima()
        anio = AnioEscolar.activo_actual()
        tab = request.GET.get("tab") if request.GET.get("tab") in dict(PESTANAS) else "mensual"
        meses = meses_del_anio(anio, hoy) if anio else []
        mes = request.GET.get("mes") if request.GET.get("mes") in dict(meses) else (meses[0][0] if meses else f"{hoy:%Y-%m}")
        a, m = (int(x) for x in mes.split("-"))

        secciones = list(Seccion.objects.filter(anio_escolar=anio).select_related("grado__nivel", "tutor"))
        grado = Grado.objects.filter(pk=request.GET.get("grado") or None).first()
        seccion = next((s for s in secciones if str(s.pk) == request.GET.get("seccion")), None)
        if seccion and grado and seccion.grado_id != grado.pk:
            seccion = None
        # Diario y mensual son por sección: si no se eligió, la primera (del grado elegido).
        if tab in ("diario", "mensual") and not seccion:
            seccion = next((s for s in secciones if not grado or s.grado_id == grado.pk), None)
        q = request.GET.get("q", "").strip()
        grado_mostrado = grado or (seccion.grado if seccion else None)

        ctx = {
            "tab": tab, "pestanas": PESTANAS, "meses": meses, "mes": mes, "mes_texto": mes_texto(a, m),
            "grados": agregados.grados_activos(), "grado": grado_mostrado, "secciones": secciones, "seccion": seccion, "q": q,
            "query": request.GET.urlencode(),
        }
        if tab == "diario":
            ctx.update(self._diario(request, seccion))
        elif tab == "mensual":
            ctx.update(self._mensual(a, m, hoy, seccion, q))
        else:
            ctx.update(self._lista(tab, a, m, hoy, grado, seccion, q))

        formato = request.GET.get("formato")
        if formato == "xlsx":
            return self._excel(ctx)
        if formato in ("imprimir", "pdf"):
            return pdf_o_impresion(
                request, "panel/impresion/reporte.html", ctx, f"reporte-{tab}-{mes}", horizontal=tab == "mensual",
            )
        return self.render("panel/reportes/index.html", ctx)

    # ------------------------------------------------------------------ pestañas
    def _diario(self, request, seccion):
        fecha = leer_fecha(request.GET.get("fecha"))
        filas = agregados.diario_seccion(seccion, fecha) if seccion else []
        conteo = {e: sum(1 for f in filas if f["registro"] and f["registro"].estado == e) for e in "PTFJ"}
        return {
            "fecha": fecha, "fecha_texto": fecha_larga(fecha, con_anio=True), "filas_diario": filas, "conteo": conteo,
            "sin_registrar": sum(1 for f in filas if not f["registro"]),
            "titulo": f"Diario · {seccion.nombre_corto} {seccion.grado.nivel}" if seccion else "Diario por sección",
            "subtitulo": fecha_larga(fecha, con_anio=True),
        }

    def _mensual(self, a, m, hoy, seccion, q):
        datos = agregados.matriz_mensual(a, m, hoy, seccion=seccion, q=q) if seccion else None
        return {
            "matriz": datos,
            "dias_cab": [(DIAS_CORTOS[d.weekday()][0], d.day) for d in datos["dias"]] if datos else [],
            "titulo": f"Resumen mensual · {seccion.nombre_corto} {seccion.grado.nivel}" if seccion else "Resumen mensual",
            "subtitulo": mes_texto(a, m),
        }

    def _lista(self, tab, a, m, hoy, grado, seccion, q):
        datos = agregados.matriz_mensual(a, m, hoy, seccion=seccion, grado=grado, q=q)
        filas = datos["riesgo"] if tab == "alertas" else sorted(
            datos["filas"], key=lambda x: (x.porcentaje is None, x.porcentaje or 0, x.nombre)
        )
        alcance = seccion.nombre_corto if seccion else (grado.nombre if grado else "Toda la I.E.")
        return {
            "matriz": datos, "filas_lista": filas,
            "titulo": f"{dict(PESTANAS)[tab]} · {alcance}",
            "subtitulo": mes_texto(a, m),
        }

    # ------------------------------------------------------------------ Excel
    def _excel(self, ctx):
        tab, mes = ctx["tab"], ctx["mes"]
        if tab == "mensual":
            if not ctx["matriz"]:
                return respuesta_archivo(b"", "vacio.xlsx", XLSX)
            contenido = excel_mensual(ctx["matriz"], ctx["titulo"].replace("Resumen mensual · ", ""), ctx["mes_texto"])
        elif tab == "diario":
            filas = [
                [
                    f"{f['matricula'].estudiante.apellidos}, {f['matricula'].estudiante.nombres}",
                    f["registro"].estado if f["registro"] else "Sin registrar",
                    hora_texto(f["registro"].marcado_en) if f["registro"] else "",
                    f["registro"].get_metodo_display() if f["registro"] else "",
                    f["justificacion"].get_motivo_display() if f["justificacion"] else "",
                    f["justificacion"].detalle if f["justificacion"] else "",
                ]
                for f in ctx["filas_diario"]
            ]
            contenido = excel_tabla(
                ctx["titulo"], ctx["subtitulo"], ["Estudiante", "Estado", "Hora", "Método", "Motivo", "Detalle"],
                filas, [36, 14, 8, 10, 18, 40],
            )
            mes = ctx["fecha"].isoformat()
        else:
            filas = [
                [x.matricula.seccion.nombre_corto, x.nombre, x.p, x.t, x.f, x.j, x.registrados, a_pct(x.porcentaje)]
                for x in ctx["filas_lista"]
            ]
            contenido = excel_tabla(
                ctx["titulo"], ctx["subtitulo"], ["Sección", "Estudiante", "P", "T", "F", "J", "Días", "% asistencia"],
                filas, [10, 36, 6, 6, 6, 6, 7, 13], pct_cols=(7,),
            )
        return respuesta_archivo(contenido, f"reporte-{tab}-{mes}.xlsx", XLSX)

