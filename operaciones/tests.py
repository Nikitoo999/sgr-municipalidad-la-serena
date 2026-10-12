from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalogos.models import AttentionSubtype, AttentionType
from sgr_core.models import InstitutionalGoal, MeasurementItem
from sgr_core.test_utils import plain_static

from .models import Employee, Task


class SeedDemoTests(TestCase):
    def test_seed_es_idempotente_y_carga_catalogos(self):
        call_command("seed_demo", verbosity=0)
        counts = (AttentionType.objects.count(), AttentionSubtype.objects.count(),
                  InstitutionalGoal.objects.count(), MeasurementItem.objects.count(),
                  Employee.objects.count(), Task.objects.count())
        call_command("seed_demo", verbosity=0)
        self.assertEqual(counts, (AttentionType.objects.count(), AttentionSubtype.objects.count(),
                                  InstitutionalGoal.objects.count(), MeasurementItem.objects.count(),
                                  Employee.objects.count(), Task.objects.count()))
        self.assertGreaterEqual(counts[0], 4)
        self.assertGreaterEqual(counts[1], 8)

    def test_seed_demo_email(self):
        call_command("seed_demo", "--demo-email", "real@correo.cl", verbosity=0)
        self.assertEqual(User.objects.get(username="jefatura_centro").email, "real@correo.cl")


@plain_static
class ScopingTests(TestCase):
    """Funcional: cada rol ve solo lo que le corresponde en el admin."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def titles(self, username):
        self.client.force_login(User.objects.get(username=username))
        r = self.client.get(reverse("admin:operaciones_task_changelist"))
        self.assertEqual(r.status_code, 200)
        return r

    def test_superusuario_ve_todas_las_tareas(self):
        r = self.titles("admin_demo")
        self.assertContains(r, "Operativo de limpieza calle Cienfuegos")
        self.assertContains(r, "Inspección de accesos a playa")

    def test_jefatura_ve_solo_su_delegacion(self):
        r = self.titles("jefatura_centro")
        self.assertContains(r, "Operativo de limpieza calle Cienfuegos")       # Centro
        self.assertNotContains(r, "Inspección de accesos a playa")             # Avenida del Mar

    def test_usuario_ve_solo_sus_tareas(self):
        r = self.titles("limitado_demo")
        self.assertContains(r, "Catastro de luminarias apagadas en Centro")
        self.assertNotContains(r, "Operativo de limpieza calle Cienfuegos")

    def test_jefatura_no_accede_a_catalogos(self):
        self.client.force_login(User.objects.get(username="jefatura_centro"))
        self.assertEqual(self.client.get(reverse("admin:catalogos_attentiontype_changelist")).status_code, 403)
