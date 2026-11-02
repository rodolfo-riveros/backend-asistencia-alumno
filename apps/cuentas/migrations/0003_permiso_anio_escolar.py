from django.db import migrations


def dar_permiso(apps, schema_editor):
    """Los roles que gestionan secciones también gestionan el año escolar y el paso de año."""
    Rol = apps.get_model("cuentas", "Rol")
    for rol in Rol.objects.all():
        permisos = list(rol.permisos or [])
        if "panel.secciones" in permisos and "panel.anio_escolar" not in permisos:
            permisos.append("panel.anio_escolar")
            rol.permisos = permisos
            rol.save(update_fields=["permisos"])


class Migration(migrations.Migration):
    dependencies = [("cuentas", "0002_rol_alter_usuario_rol")]
    operations = [migrations.RunPython(dar_permiso, migrations.RunPython.noop)]
