"""Usuarios, roles y permisos (permiso «panel.usuarios»)."""

from django.contrib import messages
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.cuentas.models import Rol, Usuario
from apps.cuentas.permisos import CODIGOS, ROL_ADMIN, agrupados

from ..forms import RolForm, UsuarioForm, generar_password_temporal
from ..mixins import PanelMixin
from .academico import _mensaje_clave


def admins_activos():
    return Usuario.objects.filter(is_active=True, rol_id=ROL_ADMIN)


def deja_sin_admin(usuario, nuevo_rol=None, activo=True) -> bool:
    """True si el cambio dejaría al sistema sin ningún administrador activo.

    Lee el estado guardado en la base (el formulario ya modificó el objeto en memoria).
    """
    original = Usuario.objects.filter(pk=usuario.pk).values("is_active", "rol_id").first() or {}
    era_admin = original.get("is_active") and original.get("rol_id") == ROL_ADMIN
    sigue_admin = activo and (nuevo_rol.codigo if nuevo_rol else original.get("rol_id")) == ROL_ADMIN
    return bool(era_admin and not sigue_admin and admins_activos().exclude(pk=usuario.pk).count() == 0)


class UsuariosView(PanelMixin, View):
    menu = "usuarios"
    permiso = "panel.usuarios"

    def get(self, request):
        usuarios = Usuario.objects.select_related("rol").order_by("rol__nombre", "apellidos", "nombres")
        rol = request.GET.get("rol")
        if rol:
            usuarios = usuarios.filter(rol_id=rol)
        q = request.GET.get("q", "").strip()
        for parte in q.split():
            usuarios = usuarios.filter(Q(nombres__icontains=parte) | Q(apellidos__icontains=parte) | Q(email__icontains=parte))
        return self.render("panel/usuarios/lista.html", {
            "usuarios": usuarios, "rol": rol, "q": q,
            "roles": Rol.objects.annotate(n=Count("usuarios")).order_by("nombre"),
        })

    def post(self, request):
        """Acciones rápidas desde la lista: restablecer clave, activar, desactivar."""
        u = get_object_or_404(Usuario, pk=request.POST.get("usuario_id"))
        accion = request.POST.get("accion")
        if accion == "restablecer":
            _restablecer(request, u)
        elif accion in ("activar", "desactivar"):
            activo = accion == "activar"
            if not activo and u == request.user:
                messages.error(request, "No puedes desactivar tu propia cuenta.")
            elif not activo and deja_sin_admin(u, activo=False):
                messages.error(request, "Es el único administrador activo: crea otro antes de desactivarlo.")
            else:
                u.is_active = activo
                u.save(update_fields=["is_active"])
                messages.success(request, f"Cuenta de {u.email} {'activada' if activo else 'desactivada'}.")
        return redirect(request.META.get("HTTP_REFERER") or "panel:usuarios")


def _restablecer(request, u):
    clave = generar_password_temporal()
    u.set_password(clave)
    u.debe_cambiar_password = True
    u.intentos_fallidos, u.bloqueado_hasta = 0, None
    u.save()
    _mensaje_clave(request, u, clave)


class UsuarioFormView(PanelMixin, View):
    menu = "usuarios"
    permiso = "panel.usuarios"

    def get(self, request, pk=None):
        u = get_object_or_404(Usuario, pk=pk) if pk else None
        inicial = {} if u else {"is_active": True, "rol": request.GET.get("rol") or "DOCENTE"}
        return self._pagina(UsuarioForm(instance=u, initial=inicial), u)

    def post(self, request, pk=None):
        u = get_object_or_404(Usuario, pk=pk) if pk else None
        if u and request.POST.get("accion") == "restablecer":
            _restablecer(request, u)
            return redirect("panel:usuario", pk=u.pk)
        form = UsuarioForm(request.POST, instance=u)
        if form.is_valid() and u and deja_sin_admin(u, form.cleaned_data["rol"], form.cleaned_data["is_active"]):
            form.add_error(None, "Es el único administrador activo: crea otro administrador antes de cambiarle el rol.")
        if not form.is_valid():
            return self._pagina(form, u)
        nuevo = form.save(commit=False)
        nuevo.is_staff = nuevo.rol_id == ROL_ADMIN
        if not u:
            clave = generar_password_temporal()
            nuevo.set_password(clave)
            nuevo.debe_cambiar_password = True
            nuevo.save()
            _mensaje_clave(request, nuevo, clave)
        else:
            nuevo.save()
            messages.success(request, f"Usuario {nuevo.email} guardado.")
        return redirect("panel:usuario", pk=nuevo.pk)

    def _pagina(self, form, u):
        return self.render("panel/usuarios/form.html", {
            "form": form, "usuario_editado": u,
            "permisos_rol": sorted(u.permisos) if u else [],
        })


class RolesView(PanelMixin, View):
    menu = "usuarios"
    permiso = "panel.usuarios"

    def get(self, request):
        roles = Rol.objects.annotate(n=Count("usuarios")).order_by("-es_sistema", "nombre")
        grupos = agrupados()
        filas = []
        for r in roles:
            tiene = r.lista_permisos()
            filas.append({"rol": r, "total": len(tiene), "n": r.n})
        return self.render("panel/usuarios/roles.html", {
            "filas": filas, "grupos": grupos, "total_permisos": len(CODIGOS),
        })


class RolFormView(PanelMixin, View):
    menu = "usuarios"
    permiso = "panel.usuarios"

    def get(self, request, pk=None):
        rol = get_object_or_404(Rol, pk=pk) if pk else None
        return self._pagina(RolForm(instance=rol, initial={} if rol else {"permisos": ["app.acceso"]}), rol)

    def post(self, request, pk=None):
        rol = get_object_or_404(Rol, pk=pk) if pk else None
        if rol and request.POST.get("accion") == "eliminar":
            if rol.es_sistema:
                messages.error(request, "Los roles iniciales no se eliminan (puedes cambiarles el nombre y los permisos).")
                return redirect("panel:rol", pk=rol.pk)
            try:
                nombre = rol.nombre
                rol.delete()
                messages.success(request, f"Rol «{nombre}» eliminado.")
                return redirect("panel:roles")
            except ProtectedError:
                messages.error(request, "No se puede eliminar: hay usuarios con este rol. Cámbiales el rol primero.")
                return redirect("panel:rol", pk=rol.pk)
        form = RolForm(request.POST, instance=rol)
        if not form.is_valid():
            return self._pagina(form, rol)
        guardado = form.save()
        messages.success(request, f"Rol «{guardado.nombre}» guardado. Los cambios se aplican al instante.")
        return redirect("panel:roles")

    def _pagina(self, form, rol):
        marcados = set(form["permisos"].value() or []) if not (rol and rol.es_admin) else set(CODIGOS)
        return self.render("panel/usuarios/rol_form.html", {
            "form": form, "rol": rol, "grupos": agrupados(), "marcados": marcados,
            "usuarios": rol.usuarios.order_by("apellidos")[:50] if rol else [],
        })
