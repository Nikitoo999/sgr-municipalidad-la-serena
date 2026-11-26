from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from operaciones.models import Task, TubeEntry
from sgr_core.models import Delegation, InstitutionalGoal, Period


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class SeedDemoDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegation = Delegation.objects.create(name="Centro")
        Delegation.objects.create(name="Las Compañías")
        cls.previous = Period.objects.create(
            name="Julio a septiembre", start_date=date(2026, 7, 1),
            end_date=date(2026, 9, 30), quarter=3, status="Cerrado",
        )
        cls.current = Period.objects.create(
            name="Octubre a diciembre", start_date=date(2026, 10, 1),
            end_date=date(2026, 12, 31), quarter=4,
        )

    def run_seed(self, **options):
        with patch("operaciones.management.commands.seed_demo_data.timezone.localdate", return_value=date(2026, 11, 20)):
            call_command("seed_demo_data", stdout=StringIO(), **options)

    def test_default_load_and_cleanup_preserve_existing_records(self):
        original = TubeEntry.objects.create(
            title="Solicitud preexistente", requester="Vecina", delegation=self.delegation,
            request_date=self.current.start_date,
        )
        self.run_seed()
        tubes = TubeEntry.objects.exclude(pk=original.pk)
        self.assertEqual(tubes.count() + Task.objects.count(), 20)
        self.assertEqual(tubes.values("delegation").distinct().order_by("delegation").count(), 2)
        self.assertEqual(
            set(tubes.values_list("status", flat=True)),
            {TubeEntry.Status.RECEIVED, TubeEntry.Status.PENDING, TubeEntry.Status.IN_PROGRESS, TubeEntry.Status.DONE},
        )
        self.assertEqual(set(Task.objects.values_list("goal__period_id", flat=True)), {self.previous.pk, self.current.pk})
        photos = [tube.proof_image for tube in tubes.filter(status=TubeEntry.Status.DONE)]
        self.assertTrue(photos)
        self.assertTrue(all(photo.storage.exists(photo.name) for photo in photos))

        with self.captureOnCommitCallbacks(execute=True):
            self.run_seed(clean=True)
        self.assertEqual(list(TubeEntry.objects.all()), [original])
        self.assertFalse(Task.objects.exists())
        self.assertFalse(InstitutionalGoal.objects.exists())
        self.assertTrue(all(not photo.storage.exists(photo.name) for photo in photos))

    def test_previous_only_load_provides_overdue_records_without_filling_current(self):
        self.run_seed(count=2, period="previous", delegation=self.delegation.code)
        tube = TubeEntry.objects.get()
        task = Task.objects.get()
        self.assertEqual(tube.delegation, self.delegation)
        self.assertEqual(tube.status, TubeEntry.Status.PENDING)
        self.assertLessEqual(tube.request_date, tube.due_date)
        self.assertLessEqual(tube.due_date, self.previous.end_date)
        self.assertEqual(task.goal.period, self.previous)
        self.assertEqual(task.goal.delegation, self.delegation)
        self.assertLessEqual(task.due_date, self.previous.end_date)
