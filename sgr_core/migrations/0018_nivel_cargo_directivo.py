"""Nivel jerárquico de los cargos directivos (organigrama por niveles).

Nivel 1: Presidencia (Presidente/a, Vicepresidente/a). Nivel 2: Directiva
(Secretario/a, Tesorero/a y sus suplentes o pro-). Nivel 3: delegaciones,
vocalías y demás cargos creados.
"""
from django.db import migrations, models


def _nivel(nombre):
    texto = nombre.lower()
    if "presid" in texto:
        return 1
    if "secretari" in texto or "tesorer" in texto:
        return 2
    return 3


def asignar_niveles(apps, schema_editor):
    DirectiveRole = apps.get_model("sgr_core", "DirectiveRole")
    for role in DirectiveRole.objects.all():
        nivel = _nivel(role.name)
        if role.level != nivel:
            role.level = nivel
            role.save(update_fields=["level"])


class Migration(migrations.Migration):

    dependencies = [
        ('sgr_core', '0017_permisos_periodos_cargos'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='directiverole',
            options={'ordering': ['level', 'order', 'name'], 'verbose_name': 'Cargo directivo', 'verbose_name_plural': 'Cargos directivos'},
        ),
        migrations.AlterModelOptions(
            name='organizationmember',
            options={'ordering': ['role__level', 'role__order', 'role__name'], 'verbose_name': 'Integrante de directiva', 'verbose_name_plural': 'Integrantes de directiva'},
        ),
        migrations.AddField(
            model_name='directiverole',
            name='level',
            field=models.PositiveSmallIntegerField(choices=[(1, 'Nivel 1 · Presidencia'), (2, 'Nivel 2 · Directiva'), (3, 'Nivel 3 · Delegaciones, vocalías y otros cargos')], default=3, verbose_name='Nivel jerárquico'),
        ),
        migrations.RunPython(asignar_niveles, migrations.RunPython.noop),
    ]
