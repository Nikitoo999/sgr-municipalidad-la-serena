from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from operaciones.models import Task, TubeEntry, TubeStatusChange
from sgr_core.models import InstitutionalGoal, Period

from .helpers import TEST_STORAGES, make_delegation, make_user


@override_settings(STORAGES=TEST_STORAGES)
class TaskTubeCreationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.admin = make_user("task-admin", is_superuser=True, is_staff=True)
        cls.delegation = make_delegation("Centro", "DEL01")
        cls.other_delegation = make_delegation("Las Compañías", "DEL02")
        cls.current = Period.objects.create(
            name="Período actual", start_date=today - timedelta(days=1), end_date=today, quarter=1,
        )
        cls.future = Period.objects.create(
            name="Período siguiente", start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=30), quarter=2,
        )
        cls.goal = InstitutionalGoal.objects.create(
            name="Mantención barrial", period=cls.future, delegation=cls.delegation,
        )

    def test_admin_creation_appears_in_the_goal_period_and_delegation_immediately(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin:operaciones_task_add"),
            {"goal": self.goal.pk, "title": "Reparar luminarias", "description": "Pasaje norte",
             "due_date": self.future.end_date.isoformat(), "status": "Pendiente", "_save": "Guardar",
             "activities-TOTAL_FORMS": "0", "activities-INITIAL_FORMS": "0"},
        )
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get()
        entry = TubeEntry.objects.get(source_task=task)
        self.assertEqual(entry.delegation, self.delegation)
        self.assertEqual(entry.status, TubeEntry.Status.PENDING)
        self.assertEqual(entry.channel, TubeEntry.Channel.DELEGATION)
        self.assertEqual(entry.due_date, task.due_date)
        self.assertEqual(entry.history.get(kind=TubeStatusChange.Kind.CREATED).changed_by, self.admin)
        card_title = f"<h3>{entry.title}</h3>"
        self.assertNotContains(self.client.get(reverse("tubes")), card_title, html=True)

        self.client.post(reverse("switch_period"), {"period": self.future.pk})
        self.client.post(reverse("switch_delegation"), {"delegation": self.delegation.pk})
        self.assertContains(self.client.get(reverse("tubes")), card_title, html=True)
        self.client.post(reverse("switch_delegation"), {"delegation": self.other_delegation.pk})
        self.assertNotContains(self.client.get(reverse("tubes")), card_title, html=True)

    def test_manual_migration_links_existing_card_without_duplicates(self):
        task = Task.objects.create(goal=self.goal, title="Limpiar plaza", due_date=self.future.end_date)
        entry = TubeEntry.objects.create(
            delegation=self.delegation, title=task.title, requester="Sistema",
            request_date=self.current.end_date, due_date=task.due_date,
            notes=f"Tarea migrada del Kanban (ID {task.pk}).",
        )
        for _ in range(2):
            call_command("migrar_tareas_a_tubos", stdout=StringIO())
        self.assertEqual(TubeEntry.objects.get(source_task=task), entry)
        self.assertEqual(TubeEntry.objects.count(), 1)
