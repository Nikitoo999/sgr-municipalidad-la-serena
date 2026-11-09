"""Migración de datos: códigos correlativos con el ancho definitivo.

Desde el Bloque 2A los códigos los asigna el sistema (``AutoCodeMixin`` en
``sgr_core.models``): DEL01, ROL01 y TAT01 usan 2 dígitos; ITM001 y SAT001
usan 3. Esta migración rellena con ceros los códigos de Ítems y Sub
atenciones que ya existían con 2 dígitos (ITM01 -> ITM001, SAT07 -> SAT007),
para que el listado no mezcle formatos. Si el código nuevo ya estuviera
ocupado, ese registro se deja tal cual. No toca otras tablas: las relaciones
usan el id, no el código.
"""
import re

from django.db import migrations

#: (modelo, prefijo, dígitos)
PADDED_CODES = (
    ("ProjectItem", "ITM", 3),
    ("AttentionSubtype", "SAT", 3),
)


def pad_codes(apps, schema_editor):
    for model_name, prefix, digits in PADDED_CODES:
        model = apps.get_model("sgr_core", model_name)
        pattern = re.compile(rf"^{prefix}(\d+)$")
        taken = set(model.objects.values_list("code", flat=True))
        for obj in model.objects.order_by("pk"):
            match = pattern.match(obj.code or "")
            if match is None:
                continue
            new_code = f"{prefix}{int(match.group(1)):0{digits}d}"
            if new_code == obj.code or new_code in taken:
                continue
            taken.discard(obj.code)
            taken.add(new_code)
            obj.code = new_code
            obj.save(update_fields=["code"])


class Migration(migrations.Migration):

    dependencies = [
        ("sgr_core", "0010_communityorganization"),
    ]

    operations = [
        migrations.RunPython(pad_codes, migrations.RunPython.noop),
    ]
