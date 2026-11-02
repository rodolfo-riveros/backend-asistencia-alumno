from datetime import timedelta

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.academico.models import Grado, Nivel
from apps.institucion.models import AnioEscolar, Configuracion, DiaNoLectivo, Institucion, Turno

from ..forms import (
    AnioEscolarForm, ConfiguracionForm, DiaNoLectivoForm, GradoForm, InstitucionForm, TurnoForm,
)
from ..mixins import PanelMixin


class ConfiguracionView(PanelMixin, View):
    """Datos de la I.E., reglas de asistencia, turnos y años escolares (solo ADMIN edita)."""

    menu = "configuracion"
    permiso = "panel.configuracion"

    def get(self, request):
        return self._pagina()

    def post(self, request):
        accion = request.POST.get("accion")
        forms = {}
        if accion == "institucion":
            f = InstitucionForm(request.POST, request.FILES, instance=Institucion.obtener())
            if f.is_valid():
                f.save()
                messages.success(request, "Datos de la institución guardados.")
                return redirect("panel:configuracion")
            forms["inst_form"] = f
        elif accion == "reglas":
            f = ConfiguracionForm(request.POST, instance=Configuracion.obtener())
            if f.is_valid():
                f.save()
                messages.success(request, "Reglas de asistencia guardadas.")
                return redirect("panel:configuracion")
            forms["conf_form"] = f
        elif accion == "turno":
            turno = get_object_or_404(Turno, pk=request.POST.get("turno_id"))
            f = TurnoForm(request.POST, instance=turno, prefix=f"t{turno.pk}")
            if f.is_valid():
                f.save()
                messages.success(request, f"Turno {turno} guardado.")
                return redirect("panel:configuracion")
            forms["turno_error"] = (turno.pk, f)
        elif accion == "anio":
            anio = AnioEscolar.objects.filter(pk=request.POST.get("anio_id")).first()
            f = AnioEscolarForm(request.POST, instance=anio, prefix="anio")
            if f.is_valid():
                f.save()
                messages.success(request, f"Año escolar {f.instance.anio} guardado.")
                return redirect("panel:configuracion")
            forms["anio_form"] = f
        elif accion == "activar_anio":
            anio = get_object_or_404(AnioEscolar, pk=request.POST.get("anio_id"))
            anio.activo = True
            anio.save()
            messages.success(request, f"El año {anio.anio} es ahora el año activo.")
            return redirect("panel:configuracion")
        return self._pagina(**forms)

    def _pagina(self, inst_form=None, conf_form=None, turno_error=None, anio_form=None):
        turnos = []
        for t in Turno.objects.all():
            form = turno_error[1] if turno_error and turno_error[0] == t.pk else TurnoForm(instance=t, prefix=f"t{t.pk}")
            turnos.append((t, form))
        return self.render("panel/configuracion/index.html", {
            "inst_form": inst_form or InstitucionForm(instance=Institucion.obtener()),
            "conf_form": conf_form or ConfiguracionForm(instance=Configuracion.obtener()),
            "turnos": turnos,
            "anios": AnioEscolar.objects.all(),
            "anio_form": anio_form or AnioEscolarForm(prefix="anio"),
        })


class CalendarioView(PanelMixin, View):
    """Feriados, vacaciones y otros días no lectivos del año activo."""

    menu = "calendario"
    permiso = "panel.calendario"

    def get(self, request):
        return self._pagina(DiaNoLectivoForm(anio=AnioEscolar.activo_actual()))

    def post(self, request):
        anio = AnioEscolar.activo_actual()
        if request.POST.get("accion") == "quitar":
            DiaNoLectivo.objects.filter(pk=request.POST.get("dia_id"), anio_escolar=anio).delete()
            messages.success(request, "Día quitado del calendario. Vuelve a ser día hábil.")
            return redirect("panel:calendario")
        form = DiaNoLectivoForm(request.POST, anio=anio)
        if not form.is_valid():
            return self._pagina(form)
        d, creados = form.cleaned_data["desde"], 0
        while d <= form.cleaned_data["hasta"]:
            if d.weekday() < 5:
                try:
                    _, nuevo = DiaNoLectivo.objects.get_or_create(
                        anio_escolar=anio, fecha=d,
                        defaults={"motivo": form.cleaned_data["motivo"], "descripcion": form.cleaned_data["descripcion"]},
                    )
                    creados += nuevo
                except IntegrityError:
                    pass
            d += timedelta(days=1)
        messages.success(request, f"Se agregaron {creados} día(s) no lectivo(s) (los fines de semana no se cuentan).")
        return redirect("panel:calendario")

    def _pagina(self, form):
        anio = AnioEscolar.activo_actual()
        dias = DiaNoLectivo.objects.filter(anio_escolar=anio).order_by("fecha")
        meses = {}
        for d in dias:
            meses.setdefault(d.fecha.month, []).append(d)
        return self.render("panel/configuracion/calendario.html", {"form": form, "meses": meses, "anio": anio, "total": dias.count()})


class NivelesView(PanelMixin, View):
    """Niveles (inicial, primaria, secundaria) y sus grados."""

    menu = "configuracion"
    permiso = "panel.configuracion"

    def get(self, request):
        return self._pagina(GradoForm(initial={"nivel": Nivel.objects.filter(activo=True).first()}))

    def post(self, request):
        accion = request.POST.get("accion")
        if accion == "nivel":
            nivel = get_object_or_404(Nivel, pk=request.POST.get("nivel_id"))
            activar = request.POST.get("activo") == "1"
            if not activar and not Nivel.objects.filter(activo=True).exclude(pk=nivel.pk).exists():
                messages.error(request, "Debe quedar al menos un nivel activo.")
            else:
                nivel.activo = activar
                nivel.save(update_fields=["activo", "actualizado_en"])
                messages.success(request, f"Nivel {nivel} {'activado' if activar else 'desactivado'}.")
            return redirect("panel:niveles")
        if accion == "editar_grado":
            grado = get_object_or_404(Grado, pk=request.POST.get("grado_id"))
            form = GradoForm(request.POST, instance=grado)
            if form.is_valid():
                form.save()
                messages.success(request, f"{grado.nombre} guardado.")
                return redirect("panel:niveles")
            messages.error(request, "; ".join(e for errs in form.errors.values() for e in errs))
            return redirect("panel:niveles")
        if accion == "eliminar_grado":
            grado = get_object_or_404(Grado, pk=request.POST.get("grado_id"))
            try:
                grado.delete()
                messages.success(request, "Grado eliminado.")
            except ProtectedError:
                messages.error(request, "No se puede eliminar: tiene secciones. Elimínalas o muévelas primero.")
            return redirect("panel:niveles")
        form = GradoForm(request.POST)
        if not form.is_valid():
            return self._pagina(form)
        form.save()
        messages.success(request, f"{form.instance.nombre} agregado.")
        return redirect("panel:niveles")

    def _pagina(self, form):
        for valor, _ in Nivel.Nombre.choices:
            Nivel.objects.get_or_create(nombre=valor, defaults={"activo": False})
        niveles = [(n, n.grados.annotate(n_secciones=Count("secciones")).order_by("orden", "numero")) for n in Nivel.objects.order_by("id")]
        return self.render("panel/configuracion/niveles.html", {"niveles": niveles, "form": form})
