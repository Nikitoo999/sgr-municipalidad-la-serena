"""Pruebas de la vista de metas por funcionario y de los cálculos (3.4)."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from operaciones.calculos import dias_habiles, meta_ajustada
from operaciones.models import EmployeeDayOff
from portal.tests.helpers import ensure_roles, make_delegation, make_employee
from portal.tests.utils import TEST_STORAGES
from sgr_core.models import Period, Position, PositionItemGoal, ProjectItem


class CalculosTests(SimpleTestCase):
    def test_trimestre_oct_dic_2026_tiene_66_dias_habiles(self):
        self.assertEqual(len(dias_habiles(date(2026, 10, 1), date(2026, 12, 31))), 66)

    def test_fin_de_semana_no_cuenta(self):
        # 3 y 4 de octubre de 2026 son sábado y domingo.
        self.assertEqual(dias_habiles(date(2026, 10, 3), date(2026, 10, 4)), [])

    def test_meta_ajustada_con_cinco_dias_libres(self):
        factor = Decimal(61) / Decimal(66)
        self.assertEqual(meta_ajustada(90, factor), Decimal("83.18"))


@override_settings(STORAGES=TEST_STORAGES)
class GoalsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02")
        cls.period = Period.objects.create(
            name="Trimestre Oct-Dic 2026",
            start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), quarter=4,
        )
        cls.cargo = Position.objects.create(code="CAR02", name="Gestor Social")
        item = ProjectItem.objects.create(code="MTX01", name="Atención social a usuario presencial")
        PositionItemGoal.objects.create(
            position=cls.cargo, item=item, period=cls.period, weight=100, target_value=90,
        )

        cls.superuser = User.objects.create_user(
            username="superadmin", password="Demo2026!", is_superuser=True, is_staff=True,
        )
        cls.ana = make_employee("ana", "10.000.001-1", cls.d1, cls.roles["ROL04"],
                                first_name="Ana", last_name="Pérez")
        cls.ana.position = cls.cargo
        cls.ana.save()
        cls.luis = make_employee("luis", "10.000.002-2", cls.d2, cls.roles["ROL04"],
                                 first_name="Luis", last_name="Rojas")
        cls.luis.position = cls.cargo
        cls.luis.save()
        cls.sin_cargo = make_employee("sincargo", "10.000.003-3", cls.d1, cls.roles["ROL04"],
                                      first_name="Sofía", last_name="Sincargo")
        cls.coord = make_employee("coord", "10.000.004-4", cls.d1, cls.roles["ROL02"])
        cls.coord.authorized_delegations.set([cls.d1])

        cls.url = reverse("goals")

    def test_exige_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp["Location"])

    def test_superadmin_ve_ficha_con_cargo_y_metas(self):
        self.client.login(username="superadmin", password="Demo2026!")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ana Pérez")
        self.assertContains(resp, "Gestor Social")
        self.assertContains(resp, "90,00")
        self.assertContains(resp, "66 días hábiles, 0 libres")

    def test_funcionario_sin_cargo_no_aparece(self):
        self.client.login(username="superadmin", password="Demo2026!")
        resp = self.client.get(self.url)
        self.assertNotContains(resp, "Sofía Sincargo")

    def test_dias_libres_reducen_la_meta_ajustada(self):
        EmployeeDayOff.objects.create(
            employee=self.ana, kind="vacation",
            start_date=date(2026, 10, 5), end_date=date(2026, 10, 9),
        )
        self.client.login(username="superadmin", password="Demo2026!")
        resp = self.client.get(self.url)
        self.assertContains(resp, "5 libres")
        self.assertContains(resp, "83,18")

    def test_coordinador_solo_ve_su_delegacion(self):
        self.client.login(username="coord", password="Demo2026!")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ana Pérez")
        self.assertNotContains(resp, "Luis Rojas")

    def test_funcionario_no_tiene_permiso(self):
        self.client.login(username="ana", password="Demo2026!")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)