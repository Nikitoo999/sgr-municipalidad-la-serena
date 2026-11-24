"""Datos: las evidencias ya validadas quedan con revisión "Aprobada"."""
from django.db import migrations


def forwards(apps, schema_editor):
    Evidence = apps.get_model("operaciones", "Evidence")
    Evidence.objects.filter(is_validated=True).update(review_status="approved")


class Migration(migrations.Migration):

    dependencies = [
        ("operaciones", "0019_atencion_validacion_tubo_historial_avisos"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
