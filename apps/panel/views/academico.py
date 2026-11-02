from datetime import time

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.academico.models import Asignacion, BloqueHorario, Curso, Seccion
from apps.estudiantes.models import Matricula
from apps.institucion.models import AnioEscolar

from ..forms import (
    DIAS_SEMANA, AsignacionForm, BloqueForm, CursoForm, DocenteForm, SeccionForm, TutoriaForm,
    generar_password_temporal,
)
from ..forms import docentes as lista_docentes
from ..mixins import PanelMixin


def anio_activo_o_aviso(request):
    anio = AnioEscolar.activo_actual()
    if anio is None:
        messages.warning(request, "No hay un año escolar activo. Créalo en Configuración.")
    return anio


# ------------------------------------------------------------------ secciones
class SeccionesView(PanelMixin, View):
    menu = "secciones"
    permiso = "panel.secciones"

    def get(self, request):
        anio = anio_activo_o_aviso(request)
        secciones = (
            Seccion.objects.filter(anio_escolar=anio)
            .select_related("grado__nivel", "turno", "tutor")
            .annotate(matriculados=Count("matriculas", filter=Q(matriculas__estado=Matricula.Estado.ACTIVA)))
        )
        grados = {}
        for s in secciones:
            grados.setdefault(s.grado, []).append(s)
        return self.render("panel/academico/secciones.html", {"grados": grados, "anio": anio, "total": len(secciones)})


class SeccionFormView(PanelMixin, View):
    menu = "secciones"
    permiso = "panel.secciones"

    def get(self, request, pk=None):
        seccion = get_object_or_404(Seccion, pk=pk) if pk else None
        return self._pagina(SeccionForm(instance=seccion, anio=self._anio(seccion)), seccion)

    def post(self, request, pk=None):
        seccion = get_object_or_404(Seccion, pk=pk) if pk else None
        form = SeccionForm(request.POST, instance=seccion, anio=self._anio(seccion))
        if not form.is_valid():
            return self._pagina(form, seccion)
        s = form.save()
        messages.success(request, f"Sección {s.nombre_corto} guardada.")
        return redirect("panel:secciones")

    def _anio(self, seccion):
        return seccion.anio_escolar if seccion else AnioEscolar.activo_actual()

    def _pagina(self, form, seccion):
        return self.render("panel/academico/seccion_form.html", {"form": form, "seccion": seccion})


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
        seccion = get_object_or_404(Seccion, pk=pk)
        form = BloqueForm(request.POST, seccion=seccion)
        if form.is_valid():
            bloque = form.save(commit=False)
            bloque.seccion = seccion
            try:
                bloque.full_clean()
            except ValidationError as e:
                form.add_error(None, e)
            else:
                bloque.save()
                messages.success(request, "Bloque agregado al horario.")
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
            form.initial.setdefault("hora_inicio", time(8, 0))
            form.initial.setdefault("hora_fin", time(8, 45))
        return self.render("panel/academico/horario.html", {
            "seccion": seccion, "form": form, "filas": filas, "dias": DIAS_SEMANA,
            "sin_asignaciones": not Asignacion.objects.filter(seccion=seccion).exists(),
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
        """Crear docente: genera usuario con contraseña temporal."""
        form = DocenteForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisa los datos del docente.")
            return self.render("panel/academico/docente_nuevo.html", {"form": form})
        docente = form.save(commit=False)
        clave = generar_password_temporal()
        docente.set_password(clave)
        docente.debe_cambiar_password = True
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
                messages.success(request, f"{docente.nombre_corto} es tutor(a) de {s.nombre_corto}{extra}.")
                return redirect("panel:docente", pk=pk)
        elif accion == "quitar_tutoria":
            Seccion.objects.filter(pk=request.POST.get("seccion_id"), tutor=docente).update(tutor=None)
            messages.success(request, "Tutoría quitada.")
            return redirect("panel:docente", pk=pk)
        elif accion == "restablecer":
            clave = generar_password_temporal()
            docente.set_password(clave)
            docente.debe_cambiar_password = True
            docente.intentos_fallidos = 0
            docente.bloqueado_hasta = None
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
    messages.success(
        request,
        f"Contraseña temporal de {usuario.email}: {clave} — entrégala al usuario; deberá cambiarla al ingresar. "
        "No se volverá a mostrar.",
    )
