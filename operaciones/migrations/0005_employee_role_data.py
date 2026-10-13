"""Migración de datos: reemplaza el rol legado (CharField) por los roles nuevos.

- "jefatura"  -> ROL03 (Delegado municipal)
- "usuario"   -> ROL04 (Funcionario)
- cualquier otro valor -> ROL04 (defensivo)

Solo toca filas cuyo role_ref aún es NULL, por lo que es idempotente.
Depende de la migración de datos de sgr_core que crea los roles base.
"""
from django.db import migrations

from sgr_core.roles import ensure_base_roles


def map_legacy_roles(apps, schema_editor):
    Employee = apps.get_model("operaciones", "Employee")
    Role = apps.get_model("sgr_core", "Role")
    RolePermission = apps.get_model("sgr_core", "RolePermission")

    # Red de seguridad: si la base no tiene los roles base, se crean.
    ensure_base_roles(Role, RolePermission)

    roles_by_code = {
        role.code: role for role in Role.objects.filter(code__in=["ROL03", "ROL04"])
    }
    delegado = roles_by_code.get("ROL03")
    funcionario = roles_by_code.get("ROL04")
    if delegado is None or funcionario is None:
        # No debería ocurrir: ensure_base_roles acaba de crearlos.
        return

    for employee in Employee.objects.filter(role_ref__isnull=True).iterator():
        employee.role_ref = delegado if employee.role == "jefatura" else funcionario
        employee.save(update_fields=["role_ref"])


def clear_role_ref(apps, schema_editor):
    Employee = apps.get_model("operaciones", "Employee")
    Employee.objects.update(role_ref=None)


class Migration(migrations.Migration):

    dependencies = [
        ("operaciones", "0004_employee_authorized_delegations_employee_role_ref"),
        ("sgr_core", "0004_delegation_codes_base_roles"),
    ]

    operations = [
        migrations.RunPython(map_legacy_roles, clear_role_ref),
    ]
