"""Carnets A4 (8 por hoja, 85,6 × 54 mm) según docs/diseno/panel-03-carnets-a4.html.

En Linux se genera PDF con WeasyPrint. En Windows (sin GTK) se usa la impresión
del navegador: «Imprimir → Guardar como PDF» produce la misma hoja.
"""

import base64
import logging
from functools import lru_cache

import segno
from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.views import View

from apps.academico.models import Seccion
from apps.estudiantes.models import Carnet, Estudiante, Matricula
from apps.institucion.models import AnioEscolar, Institucion

from ..mixins import PanelMixin

log = logging.getLogger(__name__)
POR_HOJA = 8


@lru_cache(maxsize=1)
def weasyprint_disponible() -> bool:
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


def svg_qr(contenido: str) -> str:
    return mark_safe(segno.make(contenido, error="m").svg_inline(dark="#14213D", border=0, omitsize=True))


def logo_data_uri(inst):
    if not inst.logo:
        return None
    try:
        with inst.logo.open("rb") as f:
            datos = f.read()
    except OSError:
        return None
    tipo = "image/png" if inst.logo.name.lower().endswith(".png") else "image/jpeg"
    return f"data:{tipo};base64,{base64.b64encode(datos).decode()}"


def tarjetas_de(matriculas):
    carnets = {
        c.estudiante_id: c
        for c in Carnet.objects.filter(estado=Carnet.Estado.ACTIVO, estudiante_id__in=[m.estudiante_id for m in matriculas])
    }
    tarjetas, sin_carnet = [], []
    for m in matriculas:
        c = carnets.get(m.estudiante_id)
        if c is None:
            sin_carnet.append(m.estudiante)
            continue
        tarjetas.append({
            "iniciales": m.estudiante.iniciales,
            "apellidos": m.estudiante.apellidos,
            "nombres": m.estudiante.nombres,
            "seccion": f"{m.seccion.nombre_corto} · {m.seccion.grado.nivel}",
            "qr": svg_qr(c.contenido_qr),
        })
    return tarjetas, sin_carnet


class CarnetsView(PanelMixin, View):
    menu = "carnets"
    permiso = "panel.carnets"

    def get(self, request):
        anio = AnioEscolar.activo_actual()
        secciones = (
            Seccion.objects.filter(anio_escolar=anio).select_related("grado", "turno", "tutor")
            .annotate(
                activos=Count("matriculas", distinct=True, filter=Q(matriculas__estado=Matricula.Estado.ACTIVA)),
                con_carnet=Count(
                    "matriculas__estudiante__carnets", distinct=True,
                    filter=Q(matriculas__estado=Matricula.Estado.ACTIVA, matriculas__estudiante__carnets__estado=Carnet.Estado.ACTIVO),
                ),
            )
        )
        filas = [{"s": s, "hojas": -(-s.con_carnet // POR_HOJA), "faltan": s.activos - s.con_carnet} for s in secciones]
        return self.render("panel/carnets/index.html", {
            "filas": filas, "pdf": weasyprint_disponible(), "hay_logo": bool(Institucion.obtener().logo),
        })

    def post(self, request):
        """Emite carnet a todos los matriculados de una sección que no tengan uno activo."""
        seccion = get_object_or_404(Seccion, pk=request.POST.get("seccion_id"))
        n = 0
        for m in Matricula.objects.filter(seccion=seccion, estado=Matricula.Estado.ACTIVA).select_related("estudiante"):
            if not Carnet.objects.filter(estudiante=m.estudiante, estado=Carnet.Estado.ACTIVO).exists():
                Carnet.emitir(m.estudiante)
                n += 1
        messages.success(request, f"Se emitieron {n} carnets en {seccion.nombre_corto}.")
        return redirect("panel:carnets")


class HojaCarnetsView(PanelMixin, View):
    """Hoja A4 de una sección (pk) o de un solo estudiante (estudiante=pk)."""

    menu = "carnets"
    permiso = "panel.carnets"
    por_estudiante = False

    def get(self, request, pk):
        anio = AnioEscolar.activo_actual()
        qs = Matricula.objects.filter(anio_escolar=anio, estado=Matricula.Estado.ACTIVA).select_related(
            "estudiante", "seccion__grado__nivel"
        ).order_by("estudiante__apellido_paterno", "estudiante__apellido_materno", "estudiante__nombres")
        if self.por_estudiante:
            estudiante = get_object_or_404(Estudiante, pk=pk)
            matriculas = list(qs.filter(estudiante=estudiante))
            titulo = estudiante.nombre_completo
            volver = ("panel:estudiante", pk)
        else:
            seccion = get_object_or_404(Seccion.objects.select_related("grado__nivel"), pk=pk)
            matriculas = list(qs.filter(seccion=seccion))
            titulo = f"{seccion.nombre_largo} · {seccion.grado.nivel}"
            volver = ("panel:carnets", None)

        tarjetas, sin_carnet = tarjetas_de(matriculas)
        hojas = [tarjetas[i:i + POR_HOJA] for i in range(0, len(tarjetas), POR_HOJA)]
        inst = Institucion.obtener()
        ctx = {
            "hojas": hojas, "titulo": titulo, "sin_carnet": sin_carnet, "institucion": inst,
            "anio": anio, "logo": logo_data_uri(inst),
            "pdf_disponible": weasyprint_disponible(), "query": request.GET.urlencode(),
            "volver_url": volver,
        }
        if request.GET.get("formato") == "pdf":
            if not weasyprint_disponible():
                messages.warning(request, "El PDF directo necesita WeasyPrint (servidor Linux). Usa «Imprimir → Guardar como PDF».")
                return redirect(request.path)
            from weasyprint import HTML

            html = render_to_string("panel/carnets/hoja.html", {**ctx, "modo_pdf": True}, request=request)
            pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
            respuesta = HttpResponse(pdf, content_type="application/pdf")
            respuesta["Content-Disposition"] = f'inline; filename="carnets-{pk}.pdf"'
            return respuesta
        return self.render("panel/carnets/hoja.html", ctx)
