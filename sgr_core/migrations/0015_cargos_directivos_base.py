"""Datos: cargos directivos base e ítems internos que no exigen contacto.

- Cargos base del organigrama de una organización: Presidente/a, Secretario/a
  y Tesorero/a (el preview de implementación los define como base; se pueden
  crear otros desde el portal).
- Ítems internos de la matriz (informes, inventarios, operativos, reunión de
  equipo): no exigen nombre y teléfono del usuario para sumar.
"""
from django.db import migrations

BASE_ROLES = (("Presidente/a", 1), ("Secretario/a", 2), ("Tesorero/a", 3))
INTERNAL_ITEMS = ("MTX09", "MTX10", "MTX14", "MTX15", "MTX16", "MTX17", "MTX21")


def forwards(apps, schema_editor):
    DirectiveRole = apps.get_model("sgr_core", "DirectiveRole")
    ProjectItem = apps.get_model("sgr_core", "ProjectItem")
    for name, order in BASE_ROLES:
        role, _ = DirectiveRole.objects.get_or_create(
            name=name, defaults={"is_base": True, "order": order},
        )
        if not role.is_base or role.order != order:
            role.is_base, role.order = True, order
            role.save(update_fields=["is_base", "order"])
    ProjectItem.objects.filter(code__in=INTERNAL_ITEMS).update(requires_contact=False)


class Migration(migrations.Migration):

    dependencies = [
        ("sgr_core", "0014_directiva_item_sugerido_contacto"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
