from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operaciones', '0008_attention_media_evidence_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='must_change_password',
            field=models.BooleanField(default=False, verbose_name='Debe cambiar contraseña al ingresar'),
        ),
    ]
