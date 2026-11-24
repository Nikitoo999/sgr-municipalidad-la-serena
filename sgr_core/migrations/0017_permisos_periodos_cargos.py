"""Datos: permisos de los módulos Períodos y cierre, y Cargos y metas.

Sincroniza la matriz base (idempotente) con ``sgr_core.roles.BASE_ROLES``. No
modifica el estado (Activo/Inactivo) de ningún rol existente.
"""
from django.db import migrations

from sgr_core.roles import ensure_base_roles


def sync_permissions(apps, schema_editor):
    Role = apps.get_model("sgr_core", "Role")
    RolePermission = apps.get_model("sgr_core", "RolePermission")
    ensure_base_roles(Role, RolePermission)


class Migration(migrations.Migration):

    dependencies = [
        ("sgr_core", "0016_modulos_periodos_cargos"),
    ]

    operations = [
        migrations.RunPython(sync_permissions, migrations.RunPython.noop),
    ]
