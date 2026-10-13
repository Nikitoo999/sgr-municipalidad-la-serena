"""Migración de datos: permisos de visualización para módulos pendientes.

Sincroniza la matriz base (idempotente) para que los 4 roles obtengan los
permisos ``view`` de Metas institucionales, Agenda de tareas, Cumplimiento y
Reportes según la jerarquía de ``sgr_core.roles.BASE_ROLES``. No modifica el
estado (Activo/Inactivo) de ningún rol existente.
"""
from django.db import migrations

from sgr_core.roles import ensure_base_roles


def sync_pending_module_permissions(apps, schema_editor):
    Role = apps.get_model("sgr_core", "Role")
    RolePermission = apps.get_model("sgr_core", "RolePermission")
    ensure_base_roles(Role, RolePermission)


class Migration(migrations.Migration):

    dependencies = [
        ("sgr_core", "0006_alter_rolepermission_module"),
    ]

    operations = [
        migrations.RunPython(sync_pending_module_permissions, migrations.RunPython.noop),
    ]