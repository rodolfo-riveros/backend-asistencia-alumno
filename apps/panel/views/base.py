from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from apps.cuentas.models import Usuario
from apps.institucion.models import AnioEscolar, Institucion

from ..forms import CambiarPasswordForm, LoginForm
from ..mixins import PanelMixin, primera_pagina


class LoginView(View):
    """Login del panel: solo dirección, con el mismo bloqueo por intentos que la app."""

    def get(self, request):
        if request.user.is_authenticated and request.user.acceso_panel:
            return redirect(primera_pagina(request.user))
        return self._pagina(request, LoginForm())

    def post(self, request):
        form = LoginForm(request.POST)
        if not form.is_valid():
            return self._pagina(request, form)
        email = form.cleaned_data["email"].lower().strip()
        usuario = Usuario.objects.filter(email__iexact=email).first()

        if usuario and usuario.esta_bloqueado():
            minutos = int((usuario.bloqueado_hasta - timezone.now()).total_seconds() // 60) + 1
            return self._pagina(request, form, f"Demasiados intentos fallidos. Intenta en {minutos} min.")
        if not usuario or not usuario.is_active or not usuario.check_password(form.cleaned_data["password"]):
            if usuario and usuario.is_active:
                usuario.registrar_fallo()
            return self._pagina(request, form, "Correo o contraseña incorrectos.")
        if not usuario.acceso_panel:
            return self._pagina(request, form, "Tu rol no tiene acceso al panel. Si eres docente, usa la app móvil.")

        usuario.registrar_exito()
        login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        destino = request.POST.get("next") or ""
        if url_has_allowed_host_and_scheme(destino, {request.get_host()}) and destino.startswith("/panel"):
            return redirect(destino)
        return redirect(primera_pagina(usuario))

    def _pagina(self, request, form, error=None):
        return render(request, "panel/login.html", {
            "form": form, "error": error, "next": request.GET.get("next", request.POST.get("next", "")),
            "institucion": Institucion.obtener(), "anio_activo": AnioEscolar.activo_actual(),
        })


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("panel:login")


class CambiarPasswordView(PanelMixin, View):
    def get(self, request):
        return self._pagina(CambiarPasswordForm(usuario=request.user))

    def post(self, request):
        form = CambiarPasswordForm(request.POST, usuario=request.user)
        if not form.is_valid():
            return self._pagina(form)
        u = request.user
        u.set_password(form.cleaned_data["nueva"])
        u.debe_cambiar_password = False
        u.save(update_fields=["password", "debe_cambiar_password"])
        update_session_auth_hash(request, u)
        messages.success(request, "Contraseña actualizada.")
        return redirect(primera_pagina(u))

    def _pagina(self, form):
        return render(self.request, "panel/login.html", {
            "form": form, "cambiar": True,
            "institucion": Institucion.obtener(), "anio_activo": AnioEscolar.activo_actual(),
        })


def _imagen_publica(campo):
    inst = Institucion.obtener()
    archivo = getattr(inst, campo)
    if not archivo:
        raise Http404
    r = FileResponse(archivo.open("rb"))
    r["Cache-Control"] = "public, max-age=86400"
    return r


def logo_institucion(request):
    """Logo público (login, app, carnets y reportes)."""
    return _imagen_publica("logo")


def portada_institucion(request):
    """Imagen de portada pública (pantallas de ingreso)."""
    return _imagen_publica("imagen_portada")
