from datetime import date
from io import BytesIO
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from operaciones.models import Attention, Neighbor, Task, TubeEntry
from portal.tests.helpers import TEST_STORAGES, make_delegation, make_user
from sgr_core.models import AttentionSubtype, AttentionType, InstitutionalGoal, Period


@override_settings(STORAGES=TEST_STORAGES)
class GlobalPeriodTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("period-admin", is_superuser=True)
        cls.delegation = make_delegation("Centro", "DEL01")
        cls.other_delegation = make_delegation("La Pampa", "DEL02")
        cls.old = Period.objects.create(
            name="Trimestre anterior vacío", start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30), quarter=2, status="Cerrado",
        )
        cls.previous = Period.objects.create(
            name="Trimestre anterior", start_date=date(2026, 7, 1),
            end_date=date(2026, 9, 30), quarter=3, status="Cerrado",
        )
        cls.current = Period.objects.create(
            name="Trimestre vigente", start_date=date(2026, 10, 1),
            end_date=date(2026, 12, 31), quarter=4, status="En curso",
        )
        cls.goal = InstitutionalGoal.objects.create(
            name="Meta anterior", weight=100, period=cls.previous, delegation=cls.delegation,
        )
        cls.late_task = Task.objects.create(
            goal=cls.goal, title="Tarea pendiente de septiembre", due_date=date(2026, 9, 30),
        )
        cls.late_tube = TubeEntry.objects.create(
            delegation=cls.delegation, title="Solicitud atrasada de septiembre", requester="Vecina",
            request_date=date(2026, 9, 28), due_date=date(2026, 9, 30),
        )

    def setUp(self):
        self.client.force_login(self.admin)
        today = patch("portal.period_context.timezone.localdate", return_value=date(2026, 10, 15))
        today.start()
        self.addCleanup(today.stop)

    def select(self, period):
        response = self.client.post(reverse("switch_period"), {"period": period.pk})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_switch_persists_and_displays_selected_name(self):
        self.select(self.previous)
        for route in ("home", "tasks", "goals", "achievements", "reports", "reports_charts", "tubes"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.context["sgr_active_period"], self.previous)
                self.assertContains(response, 'id="periodSel"')
                self.assertContains(
                    response, f'<option value="{self.previous.pk}" selected>{self.previous.name}</option>',
                    html=True,
                )
        self.assertEqual(self.client.get(reverse("switch_period")).status_code, 405)
        self.client.post(reverse("switch_period"), {"period": "9999999999999999999"})
        self.assertEqual(self.client.get(reverse("home")).context["sgr_active_period"], self.previous)

    def test_current_empty_only_shows_overdue_open_records_from_previous_period(self):
        Task.objects.create(goal=self.goal, title="Plazo futuro", due_date=date(2026, 10, 31))
        Task.objects.create(
            goal=self.goal, title="Tarea completada", due_date=date(2026, 9, 30), status="Completada",
        )
        for delegation, requested, due, status in (
            (self.delegation, date(2026, 6, 29), date(2026, 6, 30), "received"),
            (self.delegation, date(2026, 9, 29), date(2026, 9, 30), "done"),
            (self.delegation, date(2026, 9, 29), date(2026, 10, 30), "pending"),
            (self.other_delegation, date(2026, 9, 29), date(2026, 9, 30), "pending"),
        ):
            TubeEntry.objects.create(
                delegation=delegation, title="Solicitud excluida", requester="Vecina",
                request_date=requested, due_date=due, status=status,
            )
        self.client.post(reverse("switch_delegation"), {"delegation": self.delegation.pk})
        self.select(self.current)
        self.assertEqual(self.client.get(reverse("tasks")).context["tareas"], [self.late_task])
        tubes = self.client.get(reverse("tubes"), {"vista": "planilla"})
        self.assertEqual(list(tubes.context["pagina"]), [self.late_tube])
        self.assertEqual(self.client.get(reverse("home")).context["kpis"]["tubos_activos"], 1)

        own = TubeEntry.objects.create(
            delegation=self.delegation, title="Solicitud propia", requester="Vecina",
            request_date=self.current.start_date,
        )
        self.assertEqual(self.client.get(reverse("tasks")).context["tareas"], [])
        tubes = self.client.get(reverse("tubes"), {"vista": "planilla"})
        self.assertEqual(list(tubes.context["pagina"]), [own])

    def test_old_empty_keeps_selector_and_shows_no_records(self):
        self.select(self.old)
        for route in ("home", "tasks", "goals", "achievements", "reports", "reports_charts", "tubes"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertContains(response, "Sin registros")
                self.assertContains(response, 'id="periodSel"')
                self.assertNotContains(response, self.late_task.title)
                self.assertNotContains(response, self.late_tube.title)

    def test_attention_list_and_home_counts_follow_the_selected_period(self):
        attention_type = AttentionType.objects.create(name="Consulta")
        subtype = AttentionSubtype.objects.create(name="Consulta general", attention_type=attention_type)
        neighbor = Neighbor.objects.create(identifier="16.000.001-6", full_name="Vecina")
        numbers = []
        for day in (date(2026, 9, 30), date(2026, 10, 1)):
            attention = Attention.objects.create(
                neighbor=neighbor, delegation=self.delegation, responsible=self.admin,
                attention_type=attention_type, attention_subtype=subtype, description="Consulta",
            )
            Attention.alive.filter(pk=attention.pk).update(
                created_at=timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))
            )
            numbers.append(attention.number)

        self.select(self.current)
        response = self.client.get(reverse("attentions"))
        self.assertContains(response, numbers[1])
        self.assertNotContains(response, numbers[0])
        export = self.client.get(reverse("attentions_export"))
        self.assertEqual(export.status_code, 200)
        workbook = load_workbook(BytesIO(export.content))
        self.addCleanup(workbook.close)
        exported_numbers = [row[0] for row in workbook.active.iter_rows(min_row=2, values_only=True)]
        self.assertEqual(exported_numbers, [numbers[1]])
        self.assertEqual(self.client.get(reverse("home")).context["stat_registered"], 1)

        self.select(self.old)
        self.assertContains(self.client.get(reverse("attentions")), "Sin registros")
        self.assertEqual(self.client.get(reverse("home")).context["stat_registered"], 0)
