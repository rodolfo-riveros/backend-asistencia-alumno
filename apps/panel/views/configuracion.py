from datetime import date, timedelta

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.academico.models import Grado, Nivel
from apps.institucion import feriados as feriados_peru
from apps.institucion.models import AnioEscolar, Configuracion, DiaNoLectivo, Institucion, Turno

from ..forms import (
    ConfiguracionForm, DiaNoLectivoForm, GradoForm, InstitucionForm, TurnoForm,
)
from ..mixins import PanelMixin
from .academico import anio_elegido


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
        return self._pagina(**forms)

    def _pagina(self, inst_form=None, conf_form=None, turno_error=None):
        turnos = []
        for t in Turno.objects.all():
            form = turno_error[1] if turno_error and turno_error[0] == t.pk else TurnoForm(instance=t, prefix=f"t{t.pk}")
            turnos.append((t, form))
        return self.render("panel/configuracion/index.html", {
            "inst_form": inst_form or InstitucionForm(instance=Institucion.obtener()),
            "conf_form": conf_form or ConfiguracionForm(instance=Configuracion.obtener()),
            "turnos": turnos,
        })


class CalendarioView(PanelMixin, View):
    """Días sin clases. Los feriados nacionales se cargan solos; aquí se agregan los propios de la I.E."""

    menu = "calendario"
    permiso = "panel.calendario"

    def get(self, request):
        anio = anio_elegido(request)
        return self._pagina(anio, DiaNoLectivoForm(anio=anio))

    def post(self, request):
        anio = anio_elegido(request)
        if not anio:
            return redirect("panel:anio")
        volver = f"/panel/configuracion/calendario/?anio={anio.pk}"
        accion = request.POST.get("accion")
        if accion == "quitar":
            DiaNoLectivo.objects.filter(pk=request.POST.get("dia_id"), anio_escolar=anio).exclude(
                motivo=DiaNoLectivo.Motivo.FERIADO
            ).delete()
            messages.success(request, "Día quitado del calendario. Vuelve a ser día de clases.")
            return redirect(volver)
        if accion == "sugerido":
            fecha = date.fromisoformat(request.POST["fecha"])
            DiaNoLectivo.objects.get_or_create(
                anio_escolar=anio, fecha=fecha,
                defaults={"motivo": DiaNoLectivo.Motivo.OTRO, "descripcion": request.POST.get("descripcion", "")[:150]},
            )
            messages.success(request, f"{request.POST.get('descripcion')} agregado.")
            return redirect(volver)
        form = DiaNoLectivoForm(request.POST, anio=anio)
        if not form.is_valid():
            return self._pagina(anio, form)
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
        if creados:
            messages.success(request, f"Se agregó {creados} día(s) sin clases (sábados y domingos no se cuentan).")
        else:
            messages.warning(request, "No se agregó nada: esas fechas ya estaban registradas o caen en fin de semana.")
        return redirect(volver)

    def _pagina(self, anio, form):
        if anio:
            feriados_peru.sincronizar(anio)
        # Solo interesan los días de lunes a viernes dentro de las fechas de clases
        dias = [
            d for d in DiaNoLectivo.objects.filter(anio_escolar=anio).order_by("fecha")
            if d.fecha.weekday() < 5 and anio.fecha_inicio <= d.fecha <= anio.fecha_fin
        ] if anio else []
        nacionales_fechas = {f for f, _ in feriados_peru.feriados_nacionales(anio.anio)} if anio else set()
        nacionales = [d for d in dias if d.motivo == DiaNoLectivo.Motivo.FERIADO and d.fecha in nacionales_fechas]
        propios = [d for d in dias if d not in nacionales]
        meses = {}
        for d in propios:
            meses.setdefault(d.fecha.month, []).append(d)
        registradas = {d.fecha for d in dias}
        sugeridos = []
        if anio:
            for mes, dia, nombre in feriados_peru.SUGERIDOS_ESCOLARES:
                f = date(anio.anio, mes, dia)
                if f.weekday() < 5 and anio.fecha_inicio <= f <= anio.fecha_fin and f not in registradas:
                    sugeridos.append((f, nombre))
        return self.render("panel/configuracion/calendario.html", {
            "form": form, "anio": anio, "anios": AnioEscolar.objects.order_by("-anio"),
            "nacionales": nacionales, "meses": meses, "n_propios": len(propios), "sugeridos": sugeridos,
            "total": len(dias),
        })


class NivelesView(PanelMixin, View):
    """Niveles (inicial, primaria, secundaria) y sus grados."""

    menu = "secciones"
    permiso = "panel.secciones"

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
