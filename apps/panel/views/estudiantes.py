from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.academico.models import Grado, Seccion
from apps.asistencia.models import Registro
from apps.comun.fechas import hoy_lima, mes_texto
from apps.estudiantes.models import Apoderado, Carnet, Estudiante, Matricula
from apps.estudiantes.servicios import matricular
from apps.institucion.models import AnioEscolar
from apps.reportes.servicios import historial_mes

from ..forms import ApoderadoForm, BajaMatriculaForm, EstudianteForm
from ..mixins import PanelMixin

POR_PAGINA = 50


class EstudiantesView(PanelMixin, View):
    menu = "estudiantes"
    permiso = "panel.estudiantes"

    def get(self, request):
        anio = AnioEscolar.activo_actual()
        q = request.GET.get("q", "").strip()
        grado = request.GET.get("grado", "")
        seccion = request.GET.get("seccion", "")
        estado = request.GET.get("estado", "ACTIVA")

        matriculas = Matricula.objects.filter(anio_escolar=anio).select_related(
            "estudiante", "seccion__grado", "seccion__turno"
        )
        if estado:
            matriculas = matriculas.filter(estado=estado)
        if grado:
            matriculas = matriculas.filter(seccion__grado_id=grado)
        if seccion:
            matriculas = matriculas.filter(seccion_id=seccion)
        for parte in q.split():
            matriculas = matriculas.filter(
                Q(estudiante__apellido_paterno__icontains=parte) | Q(estudiante__apellido_materno__icontains=parte)
                | Q(estudiante__nombres__icontains=parte) | Q(estudiante__codigo_estudiante__icontains=parte)
                | Q(estudiante__dni__icontains=parte)
            )
        matriculas = matriculas.order_by(
            "seccion__grado__numero", "seccion__letra", "estudiante__apellido_paterno",
            "estudiante__apellido_materno", "estudiante__nombres",
        )
        pagina = Paginator(matriculas, POR_PAGINA).get_page(request.GET.get("pagina"))
        con_carnet = set(
            Carnet.objects.filter(estado=Carnet.Estado.ACTIVO, estudiante_id__in=[m.estudiante_id for m in pagina])
            .values_list("estudiante_id", flat=True)
        )
        sin_matricula = Estudiante.objects.filter(activo=True).exclude(matriculas__anio_escolar=anio).count()
        ctx = {
            "pagina": pagina, "con_carnet": con_carnet, "q": q, "grado": grado, "seccion": seccion, "estado": estado,
            "grados": Grado.objects.filter(nivel__activo=True),
            "secciones": Seccion.objects.filter(anio_escolar=anio).select_related("grado"),
            "sin_matricula": sin_matricula, "estados": Matricula.Estado.choices,
            "query": request.GET.urlencode(),
        }
        plantilla = "panel/estudiantes/_tabla.html" if self.es_htmx else "panel/estudiantes/lista.html"
        return self.render(plantilla, ctx)


class EstudianteNuevoView(PanelMixin, View):
    menu = "estudiantes"
    permiso = "panel.estudiantes"

    def get(self, request):
        anio = AnioEscolar.activo_actual()
        form = EstudianteForm(anio=anio, initial={"seccion": request.GET.get("seccion")})
        return self.render("panel/estudiantes/nuevo.html", {"form": form, "apoderado_form": ApoderadoForm(prefix="apo")})

    def post(self, request):
        anio = AnioEscolar.activo_actual()
        form = EstudianteForm(request.POST, anio=anio)
        apo_form = ApoderadoForm(request.POST, prefix="apo")
        apo_lleno = any(request.POST.get(f"apo-{c}") for c in ("nombre", "celular"))
        if not form.is_valid() or (apo_lleno and not apo_form.is_valid()):
            return self.render("panel/estudiantes/nuevo.html", {"form": form, "apoderado_form": apo_form})
        if not form.cleaned_data.get("seccion"):
            form.add_error("seccion", "Elige la sección para matricularlo.")
            return self.render("panel/estudiantes/nuevo.html", {"form": form, "apoderado_form": apo_form})
        with transaction.atomic():
            est = form.save()
            matricular(est, form.cleaned_data["seccion"], anio)
            if apo_lleno:
                apo = apo_form.save(commit=False)
                apo.estudiante = est
                apo.es_principal = True
                apo.save()
        messages.success(request, f"{est.nombre_completo} registrado y matriculado en {form.cleaned_data['seccion'].nombre_corto}.")
        return redirect("panel:estudiante", pk=est.pk)


class EstudianteView(PanelMixin, View):
    """Ficha: datos, apoderados, matrícula, carnet y resumen del mes."""

    menu = "estudiantes"
    permiso = "panel.estudiantes"

    def get(self, request, pk):
        est = get_object_or_404(Estudiante, pk=pk)
        anio = AnioEscolar.activo_actual()
        return self._pagina(est, EstudianteForm(instance=est, anio=anio), ApoderadoForm(prefix="nuevo"))

    def post(self, request, pk):
        est = get_object_or_404(Estudiante, pk=pk)
        anio = AnioEscolar.activo_actual()
        accion = request.POST.get("accion")
        form = EstudianteForm(instance=est, anio=anio)
        apo_form = ApoderadoForm(prefix="nuevo")
        baja_form = None

        if accion == "datos":
            form = EstudianteForm(request.POST, instance=est, anio=anio)
            if form.is_valid():
                with transaction.atomic():
                    form.save()
                    if form.cleaned_data.get("seccion"):
                        matricular(est, form.cleaned_data["seccion"], anio)
                messages.success(request, "Datos guardados.")
                return redirect("panel:estudiante", pk=pk)
        elif accion == "apoderado":
            apo_form = ApoderadoForm(request.POST, prefix="nuevo")
            if apo_form.is_valid():
                apo = apo_form.save(commit=False)
                apo.estudiante = est
                apo.save()
                if apo.es_principal:
                    est.apoderados.exclude(pk=apo.pk).update(es_principal=False)
                messages.success(request, "Apoderado agregado.")
                return redirect("panel:estudiante", pk=pk)
        elif accion == "quitar_apoderado":
            Apoderado.objects.filter(pk=request.POST.get("apoderado_id"), estudiante=est).delete()
            messages.success(request, "Apoderado quitado.")
            return redirect("panel:estudiante", pk=pk)
        elif accion == "principal":
            est.apoderados.update(es_principal=False)
            est.apoderados.filter(pk=request.POST.get("apoderado_id")).update(es_principal=True)
            return redirect("panel:estudiante", pk=pk)
        elif accion == "regenerar_carnet":
            Carnet.emitir(est)
            messages.success(request, "Carnet regenerado. El QR anterior ya no funciona: imprime el nuevo.")
            return redirect("panel:estudiante", pk=pk)
        elif accion == "baja_carnet":
            Carnet.dar_de_baja(est)
            messages.success(request, "Carnet dado de baja. Su QR ya no registra asistencia.")
            return redirect("panel:estudiante", pk=pk)
        elif accion == "baja_matricula":
            baja_form = BajaMatriculaForm(request.POST)
            m = Matricula.objects.filter(estudiante=est, anio_escolar=anio, estado=Matricula.Estado.ACTIVA).first()
            if m and baja_form.is_valid():
                with transaction.atomic():
                    m.estado = baja_form.cleaned_data["estado"]
                    m.fecha_baja = baja_form.cleaned_data["fecha_baja"]
                    m.save()
                    Carnet.dar_de_baja(est)
                messages.success(request, f"Matrícula marcada como {m.get_estado_display().lower()} y carnet dado de baja.")
                return redirect("panel:estudiante", pk=pk)
        return self._pagina(est, form, apo_form, baja_form)

    def _pagina(self, est, form, apo_form, baja_form=None):
        anio = AnioEscolar.activo_actual()
        matricula = Matricula.objects.filter(estudiante=est, anio_escolar=anio).select_related("seccion__grado__nivel", "seccion__turno").first()
        carnet = Carnet.objects.filter(estudiante=est).order_by("-emitido_en").first()
        hoy = hoy_lima()
        # Mes actual o, si aún no tiene registros, el último mes con asistencia.
        ultimo = Registro.objects.filter(matricula=matricula, sesion__fecha__lte=hoy).order_by("-sesion__fecha").values_list(
            "sesion__fecha", flat=True
        ).first() if matricula else None
        ref = ultimo if ultimo and (ultimo.year, ultimo.month) != (hoy.year, hoy.month) else hoy
        resumen = historial_mes(matricula, ref.year, ref.month, hoy) if matricula else None
        return self.render("panel/estudiantes/ficha.html", {
            "est": est, "form": form, "apo_form": apo_form,
            "baja_form": baja_form or BajaMatriculaForm(initial={"fecha_baja": hoy}),
            "matricula": matricula, "carnet": carnet,
            "historial_carnets": Carnet.objects.filter(estudiante=est).count(),
            "apoderados": est.apoderados.all(),
            "resumen": resumen, "mes": mes_texto(ref.year, ref.month) if matricula else "",
            "otras_matriculas": Matricula.objects.filter(estudiante=est).exclude(anio_escolar=anio).select_related("seccion__grado", "anio_escolar"),
        })
