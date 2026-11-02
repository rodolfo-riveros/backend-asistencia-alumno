from datetime import date, datetime, timedelta

from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views import View

from apps.academico.models import Nivel
from apps.asistencia import reglas
from apps.comun.fechas import ahora_lima, fecha_larga, hora_corta, hoy_lima
from apps.cuentas.push import enviar_push
from apps.institucion.models import Institucion, Turno
from apps.reportes import agregados
from apps.reportes.exportar import excel_dashboard

from ..mixins import PanelMixin, primera_pagina
from .carnets import weasyprint_disponible

RECORDATORIO_CADA = timedelta(minutes=15)


def leer_fecha(valor: str | None) -> date:
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date() if valor else hoy_lima()
    except ValueError:
        return hoy_lima()


def leer_turno(valor: str | None) -> str | None:
    return valor if valor in Turno.Nombre.values else None


def respuesta_archivo(contenido: bytes, nombre: str, tipo: str) -> HttpResponse:
    r = HttpResponse(contenido, content_type=tipo)
    r["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return r


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def pdf_o_impresion(request, plantilla: str, ctx: dict, nombre: str, horizontal=False):
    """PDF directo si WeasyPrint funciona (Linux); si no, la página lista para imprimir."""
    ctx = {**ctx, "horizontal": horizontal, "institucion": Institucion.obtener()}
    if request.GET.get("formato") == "pdf" and weasyprint_disponible():
        from weasyprint import HTML

        html = render_to_string(plantilla, {**ctx, "modo_pdf": True}, request=request)
        pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        r = HttpResponse(pdf, content_type="application/pdf")
        r["Content-Disposition"] = f'inline; filename="{nombre}.pdf"'
        return r
    return render(request, plantilla, {**ctx, "pdf_disponible": weasyprint_disponible()})


class DashboardView(PanelMixin, View):
    """Panel · Dashboard del día (docs/diseno/panel-01-dashboard-dia.html)."""

    menu = "dashboard"
    permiso = "panel.dashboard"

    def dispatch(self, request, *args, **kwargs):
        # Es la portada del panel: quien no ve la asistencia va a la primera sección que sí puede ver
        u = request.user
        if u.is_authenticated and u.acceso_panel and not u.puede(self.permiso) and not u.debe_cambiar_password:
            destino = primera_pagina(u)
            if destino and destino != "panel:dashboard":
                return redirect(destino)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        fecha = leer_fecha(request.GET.get("fecha"))
        turno = leer_turno(request.GET.get("turno"))
        resumen = agregados.resumen_dia(fecha, turno)
        formato = request.GET.get("formato")

        if formato == "xlsx":
            return respuesta_archivo(
                excel_dashboard(resumen, Institucion.obtener().nombre), f"asistencia-{fecha}.xlsx", XLSX,
            )

        dias = agregados.ultimos_dias(fecha, 15, turno)
        turno_ref = Turno.objects.filter(nombre=turno).first() if turno else Turno.objects.first()
        limite_puntual = None
        if turno_ref:
            limite_puntual = (datetime.combine(fecha, turno_ref.hora_ingreso) + timedelta(minutes=turno_ref.tolerancia_min)).time()
        ctx = {
            "r": resumen,
            "fecha": fecha,
            "fecha_texto": fecha_larga(fecha, con_anio=True),
            "es_hoy": fecha == hoy_lima(),
            "actualizado": hora_corta(ahora_lima()),
            "turno": turno,
            "turnos": Turno.Nombre.choices,
            "hay_varios_niveles": Nivel.objects.filter(activo=True).count() > 1,
            "limite_puntual": hora_corta(limite_puntual) if limite_puntual else "",
            "grados": [
                {
                    "nombre": f"{g['grado'].nombre.replace(' grado', '')} {g['grado'].nivel.get_nombre_display().lower()}",
                    "texto": reglas.formatear_porcentaje(g["porcentaje"]),
                    "ancho": max(0, min(100, (float(g["porcentaje"]) - 80) * 5)) if g["porcentaje"] is not None else 0,
                    "bajo": g["porcentaje"] is not None and g["porcentaje"] < 90,
                }
                for g in resumen["por_grado"]
            ],
            "dias": dias,
            "grafico": agregados.grafico_dias(dias),
            "pendientes": [x for x in resumen["secciones"] if x.sin_registrar],
            "query": request.GET.urlencode(),
            "proximo_recordatorio": self._espera_recordatorio(fecha, turno),
        }
        del_total = lambda n: reglas.formatear_porcentaje(reglas.porcentaje_asistencia(n, 0, 0, resumen["total"]))  # noqa: E731
        ctx["pct_presentes"] = del_total(resumen["presentes"])
        ctx["pct_faltas"] = del_total(resumen["faltas"])

        if formato in ("imprimir", "pdf"):
            return pdf_o_impresion(request, "panel/impresion/dashboard.html", ctx, f"asistencia-{fecha}")
        plantilla = "panel/dashboard/_contenido.html" if self.es_htmx else "panel/dashboard/index.html"
        return self.render(plantilla, ctx)

    @staticmethod
    def _espera_recordatorio(fecha, turno):
        enviado = cache.get(f"recordatorio:{fecha}:{turno or 'todos'}")
        if not enviado:
            return None
        resto = enviado + RECORDATORIO_CADA - ahora_lima()
        return max(1, int(resto.total_seconds() // 60) + 1) if resto.total_seconds() > 0 else None


class RecordarDocentesView(PanelMixin, View):
    """Push a los tutores con secciones incompletas hoy. Máximo una vez cada 15 minutos."""

    menu = "dashboard"
    permiso = "panel.dashboard"

    def post(self, request):
        fecha = hoy_lima()
        turno = leer_turno(request.POST.get("turno"))
        clave = f"recordatorio:{fecha}:{turno or 'todos'}"
        destino = redirect(f"/panel/?turno={turno}" if turno else "/panel/")

        if minutos := DashboardView._espera_recordatorio(fecha, turno):
            messages.warning(request, f"Ya se envió un recordatorio. Podrás enviar otro en {minutos} min.")
            return destino

        resumen = agregados.resumen_dia(fecha, turno)
        tutores = {x.seccion.tutor_id: x.seccion.tutor for x in resumen["secciones"] if x.sin_registrar and x.seccion.tutor}
        if not tutores:
            messages.info(request, "No hay secciones pendientes con tutor asignado.")
            return destino

        r = enviar_push(
            tutores.values(),
            "Pasa lista de hoy",
            "Aún tienes estudiantes sin registrar. Abre la app de asistencia.",
            {"tipo": "recordatorio", "fecha": fecha.isoformat()},
        )
        cache.set(clave, ahora_lima(), int(RECORDATORIO_CADA.total_seconds()))
        partes = [f"Recordatorio enviado a {r['enviados']} docente{'s' if r['enviados'] != 1 else ''}"]
        if r["sin_app"]:
            partes.append(f"{r['sin_app']} aún no activaron las notificaciones en la app")
        if r["errores"]:
            partes.append(f"{r['errores']} no se pudieron enviar (revisa la conexión del servidor)")
        (messages.success if r["enviados"] else messages.warning)(request, ". ".join(partes) + ".")
        return destino
