"""Migración de datos: permisos del módulo Organizaciones comunitarias.

Sincroniza la matriz base (idempotente) para que los 4 roles obtengan los
permisos de ``organizations`` definidos en ``sgr_core.roles.BASE_ROLES``. No
modifica el estado (Activo/Inactivo) de ningún rol existente.
"""
from django.db import migrations

from sgr_core.roles import ensure_base_roles


def sync_organization_permissions(apps, schema_editor):
    Role = apps.get_model("sgr_core", "Role")
    RolePermission = apps.get_model("sgr_core", "RolePermission")
    ensure_base_roles(Role, RolePermission)


class Migration(migrations.Migration):

    dependencies = [
        ("sgr_core", "0012_subtipo_suma_puntaje_modulo_organizaciones"),
    ]

    operations = [
        migrations.RunPython(sync_organization_permissions, migrations.RunPython.noop),
    ]
