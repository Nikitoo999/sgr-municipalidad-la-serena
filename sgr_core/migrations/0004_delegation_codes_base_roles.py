"""Migración de datos: renombra La Antena, asigna códigos de delegación
y crea los 4 roles base con su matriz de permisos (idempotente).

Funciona sobre bases que ya tienen datos (p. ej. la instancia EC2):
- "La Antena" se renombra a "La Antena-La Florida" sin duplicar la fila.
- Las delegaciones existentes reciben su código según el mapa oficial;
  cualquier otra delegación recibe el siguiente código libre (DELxx).
- Los 4 roles base (ROL01..ROL04) se crean solo si no existen y su
  matriz de permisos se sincroniza de forma idempotente.
"""
from django.db import migrations, models

from sgr_core.roles import DELEGATION_CODE_MAP, RENAMED_DELEGATIONS, ensure_base_roles


def assign_delegation_codes_and_roles(apps, schema_editor):
    Delegation = apps.get_model("sgr_core", "Delegation")
    Role = apps.get_model("sgr_core", "Role")
    RolePermission = apps.get_model("sgr_core", "RolePermission")

    # 1) Renombrar delegaciones sin duplicar la fila.
    for old_name, new_name in RENAMED_DELEGATIONS.items():
        if not Delegation.objects.filter(name=new_name).exists():
            Delegation.objects.filter(name=old_name).update(name=new_name)

    # 2) Códigos por nombre oficial; luego, a las restantes, el siguiente libre.
    used = set(
        Delegation.objects.exclude(code=None).exclude(code="")
        .values_list("code", flat=True)
    )
    for delegation in Delegation.objects.order_by("id"):
        if delegation.code:
            continue
        wanted = DELEGATION_CODE_MAP.get(delegation.name)
        if wanted and wanted not in used:
            delegation.code = wanted
            delegation.save(update_fields=["code"])
            used.add(wanted)

    next_number = 1
    for delegation in Delegation.objects.order_by("id"):
        if delegation.code:
            continue
        while f"DEL{next_number:02d}" in used:
            next_number += 1
        delegation.code = f"DEL{next_number:02d}"
        delegation.save(update_fields=["code"])
        used.add(delegation.code)
        next_number += 1

    # 3) Roles base idempotentes (solo creación/sincronización, no toma estado).
    ensure_base_roles(Role, RolePermission)


def unassign_codes(apps, schema_editor):
    Delegation = apps.get_model("sgr_core", "Delegation")
    Delegation.objects.update(code=None)


class Migration(migrations.Migration):

    dependencies = [
        ("sgr_core", "0003_role_delegation_address_delegation_code_and_more"),
    ]

    operations = [
        migrations.RunPython(assign_delegation_codes_and_roles, unassign_codes),
        migrations.AlterField(
            model_name="delegation",
            name="code",
            field=models.CharField(max_length=8, unique=True, verbose_name="Código"),
        ),
    ]
