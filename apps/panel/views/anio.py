"""Año escolar: crear, activar y pasar a los estudiantes de año (permiso «panel.anio_escolar»)."""

from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.academico.models import Asignacion, Seccion
from apps.estudiantes import promocion
from apps.estudiantes.models import Matricula
from apps.institucion import feriados as feriados_peru
from apps.institucion.models import AnioEscolar
from apps.institucion.servicios import anio_anterior, crear_anio

from ..forms import AnioFechasForm, NuevoAnioForm
from ..mixins import PanelMixin


def _anios():
    return AnioEscolar.objects.annotate(
        n_secciones=Count("secciones", distinct=True),
        n_estudiantes=Count("matriculas", filter=Q(matriculas__estado=Matricula.Estado.ACTIVA), distinct=True),
    ).order_by("-anio")


class AnioEscolarView(PanelMixin, View):
    menu = "anio"
    permiso = "panel.anio_escolar"

    def get(self, request):
        return self._pagina()

    def post(self, request):
        accion = request.POST.get("accion")
        if accion == "crear":
            form = NuevoAnioForm(request.POST)
            if not form.is_valid():
                return self._pagina(nuevo_form=form, abrir_nuevo=True)
            d = form.cleaned_data
            anio, r = crear_anio(
                d["anio"], d["fecha_inicio"], d["fecha_fin"], copiar_de=d["copiar_de"],
                copiar_secciones=d["copiar_secciones"], copiar_cursos=d["copiar_cursos"],
                feriados=True, activar=d["activar"],
            )
            partes = [f"Año {anio.anio} creado"]
            if r["secciones"]:
                partes.append(f"{r['secciones']} secciones copiadas")
            if r["asignaciones"]:
                partes.append(f"{r['asignaciones']} cursos asignados copiados")
            if r["feriados"]:
                partes.append(f"{r['feriados']} feriados agregados")
            messages.success(request, ", ".join(partes) + ". Siguiente paso: pasa a los estudiantes de año.")
            origen = d["copiar_de"] or anio_anterior(anio)
            if origen:
                return redirect(f"/panel/anio/promocion/?origen={origen.pk}&destino={anio.pk}")
            return redirect("panel:anio")
        if accion == "editar":
            anio = get_object_or_404(AnioEscolar, pk=request.POST.get("anio_id"))
            form = AnioFechasForm(request.POST, instance=anio, prefix=f"a{anio.pk}")
            if form.is_valid():
                form.save()
                n = feriados_peru.sincronizar(anio)
                messages.success(request, f"Fechas del año {anio.anio} guardadas." + (f" Se agregaron {n} feriados nacionales." if n else ""))
            else:
                messages.error(request, "; ".join(e for errs in form.errors.values() for e in errs))
            return redirect("panel:anio")
        if accion == "activar":
            anio = get_object_or_404(AnioEscolar, pk=request.POST.get("anio_id"))
            anio.activo = True
            anio.save()
            sin = Matricula.objects.filter(anio_escolar=anio, estado=Matricula.Estado.ACTIVA).count()
            messages.success(
                request,
                f"El año {anio.anio} es ahora el año activo: la app y el panel trabajan con él."
                + ("" if sin else " Aún no tiene estudiantes matriculados: pásalos de año o impórtalos."),
            )
            return redirect("panel:anio")
        return redirect("panel:anio")

    def _pagina(self, nuevo_form=None, abrir_nuevo=False):
        activo = AnioEscolar.activo_actual()
        ultimo = AnioEscolar.objects.order_by("-anio").first()
        siguiente = (ultimo.anio + 1) if ultimo else date.today().year
        anios = list(_anios())
        return self.render("panel/anio/index.html", {
            "anios": [(a, AnioFechasForm(instance=a, prefix=f"a{a.pk}")) for a in anios],
            "activo": activo,
            "nuevo_form": nuevo_form or NuevoAnioForm(initial={
                "anio": siguiente, "fecha_inicio": _lunes_desde(date(siguiente, 3, 15)),
                "fecha_fin": _viernes_hasta(date(siguiente, 12, 18)), "copiar_de": ultimo,
            }),
            # Se muestra abierto mientras no exista el año siguiente al activo
            "abrir_nuevo": abrir_nuevo or not anios or not activo or ultimo.anio <= activo.anio,
            "base": ultimo,
            "base_secciones": Seccion.objects.filter(anio_escolar=ultimo).count() if ultimo else 0,
            "base_tutores": Seccion.objects.filter(anio_escolar=ultimo, tutor__isnull=False).count() if ultimo else 0,
            "base_cursos": Asignacion.objects.filter(seccion__anio_escolar=ultimo).count() if ultimo else 0,
            "n_anios": len(anios),
            "siguiente": siguiente,
            "pendiente_promocion": self._pendiente(anios),
        })

    @staticmethod
    def _pendiente(anios):
        """Si existe un año más nuevo que el activo, sugiere pasar a los estudiantes."""
        activo = next((a for a in anios if a.activo), None)
        nuevo = anios[0] if anios else None
        if activo and nuevo and nuevo.anio > activo.anio:
            return (activo, nuevo)
        if len(anios) >= 2 and anios[0].n_estudiantes == 0 and anios[1].n_estudiantes:
            return (anios[1], anios[0])
        return None


def _lunes_desde(d):
    """Primer lunes desde la fecha (las clases suelen empezar en lunes)."""
    return d + timedelta(days=(7 - d.weekday()) % 7)


def _viernes_hasta(d):
    """Último viernes hasta la fecha."""
    return d - timedelta(days=(d.weekday() - 4) % 7)


def _par_de_anios(request):
    """(origen, destino) desde la URL o, por defecto, los dos últimos años."""
    anios = list(AnioEscolar.objects.order_by("-anio"))
    origen = AnioEscolar.objects.filter(pk=request.GET.get("origen") or request.POST.get("origen")).first()
    destino = AnioEscolar.objects.filter(pk=request.GET.get("destino") or request.POST.get("destino")).first()
    if not destino and anios:
        destino = anios[0]
    if not origen and destino:
        origen = anio_anterior(destino)
    return origen, destino, anios


class PromocionView(PanelMixin, View):
    """Paso de año: lista de salones del año anterior y a dónde pasa cada uno."""

    menu = "anio"
    permiso = "panel.anio_escolar"

    def get(self, request):
        origen, destino, anios = _par_de_anios(request)
        if not origen or not destino or origen == destino:
            messages.info(request, "Para pasar de año necesitas dos años escolares: crea primero el año nuevo.")
            return redirect("panel:anio")
        filas = promocion.avance(origen, destino)
        return self.render("panel/anio/promocion.html", {
            "origen": origen, "destino": destino, "anios": anios, "filas": filas,
            "total": sum(f["total"] for f in filas),
            "hechos": sum(f["hechos"] for f in filas),
            "sin_destino": [f for f in filas if not f["sugerida"] and not f["egresa"]],
        })

    def post(self, request):
        """«Pasar a todos con lo sugerido»: solo a quienes aún no tienen matrícula en el año nuevo."""
        origen, destino, _ = _par_de_anios(request)
        total = {"promovidos": 0, "repiten": 0, "otra": 0, "no_matriculados": 0, "quitados": 0}
        for s in Seccion.objects.filter(anio_escolar=origen):
            r = promocion.aplicar(s, destino, {})
            for k in total:
                total[k] += r[k]
        messages.success(
            request,
            f"Listo: {total['promovidos']} estudiantes pasaron de grado en {destino.anio}. "
            "Ahora revisa cada salón para marcar a quienes repiten o no continúan.",
        )
        return redirect(f"/panel/anio/promocion/?origen={origen.pk}&destino={destino.pk}")


class PromocionSeccionView(PanelMixin, View):
    """Un salón: todos pasan al grado siguiente; se cambia solo a quien repite o no continúa."""

    menu = "anio"
    permiso = "panel.anio_escolar"

    def get(self, request, pk):
        origen_seccion = get_object_or_404(Seccion.objects.select_related("grado__nivel", "anio_escolar"), pk=pk)
        _, destino, _ = _par_de_anios(request)
        return self._pagina(origen_seccion, destino)

    def post(self, request, pk):
        origen_seccion = get_object_or_404(Seccion.objects.select_related("grado__nivel", "anio_escolar"), pk=pk)
        _, destino, _ = _par_de_anios(request)
        decisiones = {
            int(k.split("_", 1)[1]): v for k, v in request.POST.items() if k.startswith("m_") and k[2:].isdigit()
        }
        r = promocion.aplicar(origen_seccion, destino, decisiones)
        partes = []
        if r["promovidos"]:
            partes.append(f"{r['promovidos']} pasan de grado")
        if r["repiten"]:
            partes.append(f"{r['repiten']} repiten")
        if r["otra"]:
            partes.append(f"{r['otra']} van a otra sección")
        if r["no_matriculados"]:
            partes.append(f"{r['no_matriculados']} no se matriculan")
        messages.success(request, f"{origen_seccion.nombre_corto} guardado: " + ", ".join(partes or ["sin cambios"]) + ".")
        return redirect(f"/panel/anio/promocion/?origen={origen_seccion.anio_escolar_id}&destino={destino.pk}")

    def _pagina(self, origen_seccion, destino):
        secciones = list(Seccion.objects.filter(anio_escolar=destino).select_related("grado").order_by(
            "grado__orden", "grado__numero", "letra"
        ))
        siguiente = promocion.grado_siguiente(origen_seccion.grado)
        grupos = [
            ("Pasa de grado", [s for s in secciones if siguiente and s.grado_id == siguiente.pk]),
            ("Repite el grado", [s for s in secciones if s.grado_id == origen_seccion.grado_id]),
            ("Otra sección", [s for s in secciones if s.grado_id not in (origen_seccion.grado_id, siguiente.pk if siguiente else None)]),
        ]
        return self.render("panel/anio/promocion_seccion.html", {
            "origen_seccion": origen_seccion, "destino": destino,
            "filas": promocion.filas_de(origen_seccion, destino),
            "grupos": [(t, ss) for t, ss in grupos if ss],
            "sugerida": promocion.seccion_sugerida(origen_seccion, destino),
            "repite": promocion.seccion_repite(origen_seccion, destino),
            "egresa": siguiente is None,
            "no_matricular": promocion.NO_MATRICULAR,
        })
