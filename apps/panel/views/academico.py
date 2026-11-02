from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.academico.models import Asignacion, BloqueHorario, Curso, Grado, Seccion
from apps.academico.servicios import tutor_dicta_todo
from apps.estudiantes.models import Matricula
from apps.institucion.models import AnioEscolar, Turno

from ..forms import (
    DIAS_SEMANA, AsignacionForm, BloqueForm, CursoForm, DocenteForm, SeccionForm, TutoriaForm,
    poner_clave_inicial,
)
from ..forms import docentes as lista_docentes
from ..mixins import PanelMixin


def anio_activo_o_aviso(request):
    anio = AnioEscolar.activo_actual()
    if anio is None:
        messages.warning(request, "No hay un año escolar activo. Créalo en Año escolar.")
    return anio


# ------------------------------------------------------------------ secciones
def anio_elegido(request):
    """Año que se está viendo: el de ?anio= o el activo. Permite preparar el año siguiente."""
    elegido = AnioEscolar.objects.filter(pk=request.GET.get("anio") or request.POST.get("anio")).first()
    return elegido or anio_activo_o_aviso(request)


class SeccionesView(PanelMixin, View):
    menu = "secciones"
    permiso = "panel.secciones"

    def get(self, request):
        anio = anio_elegido(request)
        secciones = (
            Seccion.objects.filter(anio_escolar=anio)
            .select_related("grado__nivel", "turno", "tutor")
            .annotate(matriculados=Count("matriculas", filter=Q(matriculas__estado=Matricula.Estado.ACTIVA)))
            .order_by("letra")
        )
        por_grado = {}
        for sec in secciones:
            por_grado.setdefault(sec.grado_id, []).append(sec)
        grados = [(g, por_grado.get(g.pk, [])) for g in Grado.objects.filter(nivel__activo=True).select_related("nivel")]
        return self.render("panel/academico/secciones.html", {
            "grados": grados, "anio": anio, "total": len(secciones),
            "anios": AnioEscolar.objects.order_by("-anio"),
            "sin_tutor": sum(1 for sec in secciones if not sec.tutor_id),
        })


class SeccionFormView(PanelMixin, View):
    menu = "secciones"
    permiso = "panel.secciones"

    def get(self, request, pk=None):
        seccion = get_object_or_404(Seccion, pk=pk) if pk else None
        anio = self._anio(request, seccion)
        inicial = {}
        if not seccion:
            grado = Grado.objects.filter(pk=request.GET.get("grado")).first()
            if grado:
                usadas = set(Seccion.objects.filter(anio_escolar=anio, grado=grado).values_list("letra", flat=True))
                letra = next((c for c in "ABCDEFGHIJ" if c not in usadas), "")
                inicial = {"grado": grado.pk, "letra": letra, "turno": Turno.objects.order_by("hora_ingreso").first()}
        return self._pagina(SeccionForm(instance=seccion, anio=anio, initial=inicial), seccion, anio)

    def post(self, request, pk=None):
        seccion = get_object_or_404(Seccion, pk=pk) if pk else None
        anterior = seccion.tutor if seccion else None
        anio = self._anio(request, seccion)
        form = SeccionForm(request.POST, instance=seccion, anio=anio)
        if not form.is_valid():
            return self._pagina(form, seccion, anio)
        sec = form.save()
        extra = ""
        if sec.tutor and form.cleaned_data.get("tutor_dicta_todo"):
            r = tutor_dicta_todo(sec, anterior)
            if r["nuevos"] or r["pasados"]:
                extra = f" {sec.tutor.nombre_corto} dicta {r['nuevos'] + r['pasados']} curso(s) más."
        messages.success(request, f"Sección {sec.nombre_corto} de {anio.anio} guardada.{extra}")
        if request.POST.get("otra"):
            return redirect(f"/panel/secciones/nueva/?anio={anio.pk}&grado={sec.grado_id}")
        return redirect(f"/panel/secciones/?anio={anio.pk}")

    def _anio(self, request, seccion):
        if seccion:
            return seccion.anio_escolar
        return AnioEscolar.objects.filter(pk=request.GET.get("anio") or request.POST.get("anio")).first() or AnioEscolar.activo_actual()

    def _pagina(self, form, seccion, anio):
        return self.render("panel/academico/seccion_form.html", {"form": form, "seccion": seccion, "anio": anio})


class SeccionEliminarView(PanelMixin, View):
    menu = "secciones"
    permiso = "panel.secciones"

    def post(self, request, pk):
        seccion = get_object_or_404(Seccion, pk=pk)
        nombre = seccion.nombre_corto
        try:
            Asignacion.objects.filter(seccion=seccion, bloques__isnull=True).delete()
            seccion.delete()
            messages.success(request, f"Sección {nombre} eliminada.")
        except ProtectedError:
            messages.error(request, f"No se puede eliminar {nombre}: tiene estudiantes, horario o asistencia registrada.")
        return redirect("panel:secciones")


# ------------------------------------------------------------------ cursos y horarios
class CursosView(PanelMixin, View):
    menu = "cursos"
    permiso = "panel.cursos"

    def get(self, request):
        return self._pagina(CursoForm())

    def post(self, request):
        curso = get_object_or_404(Curso, pk=request.POST["curso_id"]) if request.POST.get("curso_id") else None
        form = CursoForm(request.POST, instance=curso)
        if not form.is_valid():
            return self._pagina(form)
        form.save()
        messages.success(request, "Curso guardado.")
        return redirect("panel:cursos")

    def _pagina(self, form):
        anio = AnioEscolar.activo_actual()
        cursos = Curso.objects.annotate(n_asignaciones=Count("asignaciones", filter=Q(asignaciones__seccion__anio_escolar=anio)))
        secciones = (
            Seccion.objects.filter(anio_escolar=anio).select_related("grado", "turno")
            .annotate(n_bloques=Count("bloques"))
        )
        return self.render("panel/academico/cursos.html", {"form": form, "cursos": cursos, "secciones": secciones})


class HorarioView(PanelMixin, View):
    """Horario semanal de una sección (L–V × bloques) con detección de choques."""

    menu = "cursos"
    permiso = "panel.cursos"

    def get(self, request, pk):
        seccion = get_object_or_404(Seccion.objects.select_related("grado", "turno"), pk=pk)
        return self._pagina(seccion, BloqueForm(seccion=seccion))

    def post(self, request, pk):
        seccion = get_object_or_404(Seccion.objects.select_related("grado", "turno", "tutor"), pk=pk)
        form = BloqueForm(request.POST, seccion=seccion)
        if form.is_valid():
            d = form.cleaned_data
            try:
                with transaction.atomic():
                    asig, _ = Asignacion.objects.get_or_create(seccion=seccion, curso=d["curso"], defaults={"docente": d["docente"]})
                    if asig.docente_id != d["docente"].pk:
                        asig.docente = d["docente"]  # el curso pasa a otro docente (también sus otros bloques)
                        asig.save(update_fields=["docente", "actualizado_en"])
                    for dia in d["dias"]:
                        bloque = BloqueHorario(seccion=seccion, asignacion=asig, dia_semana=dia,
                                               hora_inicio=d["hora_inicio"], hora_fin=d["hora_fin"])
                        bloque.full_clean()
                        bloque.save()
            except ValidationError as e:
                form.add_error(None, e)
            else:
                n = len(d["dias"])
                messages.success(request, f"{d['curso']} agregado en {n} día{'s' if n > 1 else ''}.")
                return redirect("panel:horario", pk=seccion.pk)
        return self._pagina(seccion, form)

    def _pagina(self, seccion, form):
        bloques = list(
            BloqueHorario.objects.filter(seccion=seccion).select_related("asignacion__curso", "asignacion__docente")
        )
        franjas = sorted({(b.hora_inicio, b.hora_fin) for b in bloques})
        filas = []
        for inicio, fin in franjas:
            celdas = [
                [b for b in bloques if b.dia_semana == dia and b.hora_inicio == inicio and b.hora_fin == fin]
                for dia, _ in DIAS_SEMANA
            ]
            filas.append({"inicio": inicio, "fin": fin, "celdas": celdas})
        if not form.is_bound:
            # Sugerir el bloque siguiente al último registrado
            ultimo = max((b.hora_fin for b in bloques), default=None)
            inicio = ultimo or time(8, 0)
            fin = (datetime.combine(date.today(), inicio) + timedelta(minutes=45)).time()
            form.initial.update({"hora_inicio": inicio, "hora_fin": fin, "dias": [n for n, _ in DIAS_SEMANA]})
        return self.render("panel/academico/horario.html", {
            "seccion": seccion, "form": form, "filas": filas, "dias": DIAS_SEMANA,
            "asignaciones": Asignacion.objects.filter(seccion=seccion).select_related("curso", "docente").order_by("curso__nombre"),
        })


class BloqueEliminarView(PanelMixin, View):
    menu = "cursos"
    permiso = "panel.cursos"

    def post(self, request, pk):
        bloque = get_object_or_404(BloqueHorario, pk=pk)
        seccion_id = bloque.seccion_id
        try:
            bloque.delete()
            messages.success(request, "Bloque eliminado.")
        except ProtectedError:
            messages.error(request, "No se puede eliminar: ya tiene asistencia registrada.")
        return redirect("panel:horario", pk=seccion_id)


# ------------------------------------------------------------------ docentes
class DocentesView(PanelMixin, View):
    menu = "docentes"
    permiso = "panel.docentes"

    def get(self, request):
        anio = AnioEscolar.activo_actual()
        docentes = lista_docentes(activos=False).order_by("-is_active", "apellidos", "nombres")
        tutorias, asignaciones = {}, {}
        for s in Seccion.objects.filter(anio_escolar=anio, tutor__isnull=False).select_related("grado"):
            tutorias.setdefault(s.tutor_id, []).append(s.nombre_corto)
        for a in Asignacion.objects.filter(seccion__anio_escolar=anio).values("docente_id").annotate(n=Count("id")):
            asignaciones[a["docente_id"]] = a["n"]
        filas = [
            {"d": d, "tutorias": tutorias.get(d.id, []), "asignaciones": asignaciones.get(d.id, 0)} for d in docentes
        ]
        return self.render("panel/academico/docentes.html", {"filas": filas, "form": DocenteForm(initial={"is_active": True, "rol": "DOCENTE"})})

    def post(self, request):
        """Crear docente: su contraseña es su DNI."""
        form = DocenteForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisa los datos del docente.")
            return self.render("panel/academico/docente_nuevo.html", {"form": form})
        docente = form.save(commit=False)
        clave = poner_clave_inicial(docente)
        docente.save()
        _mensaje_clave(request, docente, clave)
        return redirect("panel:docente", pk=docente.pk)


class DocenteNuevoView(PanelMixin, View):
    menu = "docentes"
    permiso = "panel.docentes"

    def get(self, request):
        return self.render("panel/academico/docente_nuevo.html", {"form": DocenteForm(initial={"is_active": True, "rol": "DOCENTE"})})


class DocenteView(PanelMixin, View):
    menu = "docentes"
    permiso = "panel.docentes"

    def get(self, request, pk):
        docente = get_object_or_404(lista_docentes(activos=False), pk=pk)
        anio = AnioEscolar.activo_actual()
        return self._pagina(docente, DocenteForm(instance=docente), AsignacionForm(docente=docente, anio=anio),
                            TutoriaForm(anio=anio))

    def post(self, request, pk):
        docente = get_object_or_404(lista_docentes(activos=False), pk=pk)
        anio = AnioEscolar.activo_actual()
        accion = request.POST.get("accion")
        datos_form = DocenteForm(instance=docente)
        asig_form = AsignacionForm(docente=docente, anio=anio)
        tut_form = TutoriaForm(anio=anio)

        if accion == "datos":
            datos_form = DocenteForm(request.POST, instance=docente)
            if datos_form.is_valid():
                datos_form.save()
                messages.success(request, "Datos del docente guardados.")
                return redirect("panel:docente", pk=pk)
        elif accion == "asignar":
            asig_form = AsignacionForm(request.POST, docente=docente, anio=anio)
            if asig_form.is_valid():
                Asignacion.objects.create(docente=docente, **asig_form.cleaned_data)
                messages.success(request, "Curso asignado.")
                return redirect("panel:docente", pk=pk)
        elif accion == "quitar":
            asig = get_object_or_404(Asignacion, pk=request.POST.get("asignacion_id"), docente=docente)
            try:
                asig.delete()
                messages.success(request, "Asignación quitada.")
            except ProtectedError:
                messages.error(request, "No se puede quitar: el curso tiene bloques de horario. Quítalos primero.")
            return redirect("panel:docente", pk=pk)
        elif accion == "tutoria":
            tut_form = TutoriaForm(request.POST, anio=anio)
            if tut_form.is_valid():
                s = tut_form.cleaned_data["seccion"]
                anterior = s.tutor
                s.tutor = docente
                s.save(update_fields=["tutor", "actualizado_en"])
                extra = f" (antes: {anterior.nombre_completo})" if anterior and anterior != docente else ""
                if tut_form.cleaned_data["todos_cursos"]:
                    tutor_dicta_todo(s, anterior)
                    extra += " Dicta todos sus cursos."
                messages.success(request, f"{docente.nombre_corto} es tutor(a) de {s.nombre_corto}{extra}.")
                return redirect("panel:docente", pk=pk)
        elif accion == "cursos_tutoria":
            s = get_object_or_404(Seccion, pk=request.POST.get("seccion_id"), tutor=docente)
            r = tutor_dicta_todo(s)
            messages.success(request, f"{docente.nombre_corto} dicta {r['nuevos']} curso(s) más en {s.nombre_corto}."
                             if r["nuevos"] else f"Todos los cursos de {s.nombre_corto} ya tienen docente.")
            return redirect("panel:docente", pk=pk)
        elif accion == "quitar_tutoria":
            Seccion.objects.filter(pk=request.POST.get("seccion_id"), tutor=docente).update(tutor=None)
            messages.success(request, "Tutoría quitada.")
            return redirect("panel:docente", pk=pk)
        elif accion == "restablecer":
            clave = poner_clave_inicial(docente)
            docente.save()
            _mensaje_clave(request, docente, clave)
            return redirect("panel:docente", pk=pk)
        return self._pagina(docente, datos_form, asig_form, tut_form)

    def _pagina(self, docente, datos_form, asig_form, tut_form):
        anio = AnioEscolar.activo_actual()
        return self.render("panel/academico/docente.html", {
            "docente": docente,
            "datos_form": datos_form,
            "asig_form": asig_form,
            "tut_form": tut_form,
            "tutorias": Seccion.objects.filter(anio_escolar=anio, tutor=docente).select_related("grado", "turno"),
            "asignaciones": Asignacion.objects.filter(docente=docente, seccion__anio_escolar=anio)
            .select_related("seccion__grado", "curso").order_by("seccion__grado__numero", "seccion__letra", "curso__nombre"),
        })


def _mensaje_clave(request, usuario, clave):
    if clave is None:
        messages.success(request, f"Listo: {usuario.nombre_corto} entra con su correo {usuario.email} y su DNI como contraseña.")
        return
    messages.success(
        request,
        f"Contraseña temporal de {usuario.email}: {clave} — entrégala al usuario; deberá cambiarla al ingresar. "
        "No se volverá a mostrar.",
    )
