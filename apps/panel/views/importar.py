import secrets

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import View

from apps.institucion.models import AnioEscolar

from .. import importacion
from ..forms import ImportarForm
from ..mixins import PanelMixin

CLAVE_SESION = "importacion_estudiantes"


class ImportarView(PanelMixin, View):
    menu = "importar"
    permiso = "panel.importar"

    def get(self, request):
        return self.render("panel/importar/subir.html", {"form": ImportarForm()})

    def post(self, request):
        anio = AnioEscolar.activo_actual()
        if anio is None:
            messages.error(request, "Primero activa un año escolar en Configuración.")
            return redirect("panel:importar")

        if request.POST.get("accion") == "confirmar":
            return self._confirmar(request, anio)

        form = ImportarForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render("panel/importar/subir.html", {"form": form})
        resultado = importacion.leer_excel(form.cleaned_data["archivo"], anio)
        token = secrets.token_urlsafe(8)
        request.session[CLAVE_SESION] = {"token": token, "filas": importacion.serializar(resultado.filas)}
        return self.render("panel/importar/vista_previa.html", {
            "resultado": resultado, "token": token, "nombre_archivo": form.cleaned_data["archivo"].name,
            "nuevos": sum(1 for f in resultado.validas if f.accion == "Nuevo"),
            "actualizar": sum(1 for f in resultado.validas if f.accion == "Actualizar"),
        })

    def _confirmar(self, request, anio):
        datos = request.session.get(CLAVE_SESION)
        if not datos or datos["token"] != request.POST.get("token"):
            messages.error(request, "La vista previa expiró. Sube el archivo de nuevo.")
            return redirect("panel:importar")
        if not datos["filas"]:
            messages.error(request, "No hay filas válidas para importar.")
            return redirect("panel:importar")
        resumen = importacion.importar(datos["filas"], anio)
        del request.session[CLAVE_SESION]
        messages.success(
            request,
            f"Importación completa: {resumen['nuevos']} estudiantes nuevos y {resumen['actualizados']} actualizados. "
            "Los nuevos ya tienen carnet QR.",
        )
        return redirect("panel:estudiantes")


class PlantillaView(PanelMixin, View):
    permiso = "panel.importar"

    def get(self, request):
        respuesta = HttpResponse(
            importacion.plantilla_xlsx(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        respuesta["Content-Disposition"] = 'attachment; filename="plantilla_estudiantes.xlsx"'
        return respuesta
