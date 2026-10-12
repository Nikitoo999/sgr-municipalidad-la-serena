from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Achievement, Delegation, InstitutionalGoal, MeasurementItem, Period
from .test_utils import plain_static


class BaseData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("root", "root@ejemplo.cl", "Clave-Test-123")
        cls.deleg = Delegation.objects.create(name="Centro")
        cls.period = Period.objects.create(
            name="T3", start_date=date(2026, 7, 1), end_date=date(2026, 9, 30), quarter=3)

    def setUp(self):
        self.client.force_login(self.admin)

    def goal_data(self, **over):
        data = {"name": "Meta A", "description": "", "weight": "60", "period": self.period.pk,
                "delegation": self.deleg.pk,
                "measurement_items-TOTAL_FORMS": "0", "measurement_items-INITIAL_FORMS": "0",
                "measurement_items-MIN_NUM_FORMS": "0", "measurement_items-MAX_NUM_FORMS": "1000"}
        data.update(over)
        return data


@plain_static
class GoalCrudTests(BaseData):
    def test_crear_meta(self):
        r = self.client.post(reverse("admin:sgr_core_institutionalgoal_add"), self.goal_data())
        self.assertEqual(r.status_code, 302)
        self.assertEqual(InstitutionalGoal.objects.get().weight, Decimal("60.00"))

    def test_ponderacion_fuera_de_rango(self):
        for bad in ("-1", "100.01", "150"):
            r = self.client.post(reverse("admin:sgr_core_institutionalgoal_add"), self.goal_data(weight=bad))
            self.assertEqual(r.status_code, 200, bad)
            self.assertContains(r, "entre 0 y 100")
        self.assertEqual(InstitutionalGoal.objects.count(), 0)

    def test_suma_de_ponderaciones_no_supera_100(self):
        InstitutionalGoal.objects.create(name="Meta A", weight=60, period=self.period, delegation=self.deleg)
        r = self.client.post(reverse("admin:sgr_core_institutionalgoal_add"),
                             self.goal_data(name="Meta B", weight="50"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "sumarían 110")
        # 40 sí cabe (60 + 40 = 100)
        r = self.client.post(reverse("admin:sgr_core_institutionalgoal_add"),
                             self.goal_data(name="Meta B", weight="40"))
        self.assertEqual(r.status_code, 302)

    def test_editar_meta_no_cuenta_su_propio_peso(self):
        g = InstitutionalGoal.objects.create(name="Meta A", weight=100, period=self.period, delegation=self.deleg)
        r = self.client.post(reverse("admin:sgr_core_institutionalgoal_change", args=[g.pk]),
                             self.goal_data(weight="90"))
        self.assertEqual(r.status_code, 302)
        g.refresh_from_db()
        self.assertEqual(g.weight, Decimal("90.00"))

    def test_otra_delegacion_tiene_su_propio_100(self):
        otra = Delegation.objects.create(name="Rural")
        InstitutionalGoal.objects.create(name="Meta A", weight=100, period=self.period, delegation=self.deleg)
        r = self.client.post(reverse("admin:sgr_core_institutionalgoal_add"),
                             self.goal_data(name="Meta R", weight="100", delegation=otra.pk))
        self.assertEqual(r.status_code, 302)

    def test_listado_busqueda_y_contador_de_items(self):
        g = InstitutionalGoal.objects.create(name="Meta A", weight=60, period=self.period, delegation=self.deleg)
        MeasurementItem.objects.create(goal=g, name="I1", unit_of_measure="u")
        MeasurementItem.objects.create(goal=g, name="I2", unit_of_measure="u")
        r = self.client.get(reverse("admin:sgr_core_institutionalgoal_changelist") + "?q=Centro")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Meta A")

    def test_borrar_meta(self):
        g = InstitutionalGoal.objects.create(name="Meta A", weight=60, period=self.period, delegation=self.deleg)
        r = self.client.post(reverse("admin:sgr_core_institutionalgoal_delete", args=[g.pk]), {"post": "yes"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(InstitutionalGoal.objects.count(), 0)


@plain_static
class ItemCrudTests(BaseData):
    def setUp(self):
        super().setUp()
        self.goal = InstitutionalGoal.objects.create(
            name="Meta A", weight=60, period=self.period, delegation=self.deleg)

    def item_data(self, **over):
        data = {"goal": self.goal.pk, "name": "Operativos", "unit_of_measure": "operativos",
                "baseline": "0", "target_value": "12"}
        data.update(over)
        return data

    def test_crear_editar_borrar_item(self):
        r = self.client.post(reverse("admin:sgr_core_measurementitem_add"), self.item_data())
        self.assertEqual(r.status_code, 302)
        item = MeasurementItem.objects.get()
        r = self.client.post(reverse("admin:sgr_core_measurementitem_change", args=[item.pk]),
                             self.item_data(target_value="20"))
        self.assertEqual(r.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.target_value, Decimal("20.00"))
        r = self.client.post(reverse("admin:sgr_core_measurementitem_delete", args=[item.pk]), {"post": "yes"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(MeasurementItem.objects.count(), 0)

    def test_valores_negativos_rechazados(self):
        r = self.client.post(reverse("admin:sgr_core_measurementitem_add"),
                             self.item_data(baseline="-1", target_value="-5"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "no puede ser negativo")
        self.assertEqual(MeasurementItem.objects.count(), 0)

    def test_nombre_duplicado_en_la_misma_meta(self):
        MeasurementItem.objects.create(goal=self.goal, name="Operativos", unit_of_measure="u")
        r = self.client.post(reverse("admin:sgr_core_measurementitem_add"), self.item_data(name="operativos"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "ya tiene un ítem con ese nombre")

    def test_busqueda_por_nombre_y_meta(self):
        MeasurementItem.objects.create(goal=self.goal, name="Operativos", unit_of_measure="u")
        url = reverse("admin:sgr_core_measurementitem_changelist")
        self.assertContains(self.client.get(url + "?q=Operativos"), "Operativos")
        self.assertContains(self.client.get(url + "?q=Meta+A"), "Operativos")

    def test_porcentaje_de_cumplimiento_0_a_100(self):
        url = reverse("admin:sgr_core_achievement_add")
        r = self.client.post(url, {"goal": self.goal.pk, "percentage": "101"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "entre 0 y 100")
        r = self.client.post(url, {"goal": self.goal.pk, "percentage": "80"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Achievement.objects.get().percentage, Decimal("80.00"))
