"""Cierre de la migración de rol de Employee:

1. Elimina el campo legado (CharField "role").
2. Renombra "role_ref" (FK nullable) a "role".
3. Hace obligatorio el campo (null=False).

El estado final coincide exactamente con el modelo.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("operaciones", "0005_employee_role_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="employee",
            name="role",
        ),
        migrations.RenameField(
            model_name="employee",
            old_name="role_ref",
            new_name="role",
        ),
        migrations.AlterField(
            model_name="employee",
            name="role",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="employees",
                to="sgr_core.role",
                verbose_name="Rol",
            ),
        ),
    ]
