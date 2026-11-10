from datetime import date
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from sgr_core.models import Period, Position, Role
from portal.tests.helpers import ensure_roles, make_delegation, make_employee, DEMO_PASSWORD, TEST_STORAGES


@override_settings(STORAGES=TEST_STORAGES)
class ReportsViewTests(TestCase):
    def setUp(self):
        ensure_roles()
        self.delegation = make_delegation("Delegación Centro", "DEL01")
        self.period = Period.objects.create(
            name="Trimestre Oct-Dic 2026",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 12, 31),
            quarter=4
        )
        
        role_superadmin = Role.objects.get(code="ROL01")
        role_delegado = Role.objects.get(code="ROL03")
        role_funcionario = Role.objects.get(code="ROL04")

        self.pos_delegado = Position.objects.create(code="CAR01", name="Delegado", is_evaluated=False)
        self.pos_gestor = Position.objects.create(code="CAR02", name="Gestor Social", is_evaluated=True)

        self.admin_user = make_employee("admin_test", "11111111-1", self.delegation, role_superadmin)
        
        self.emp_delegado = make_employee("delegado_test", "22222222-2", self.delegation, role_delegado)
        self.emp_delegado.position = self.pos_delegado
        self.emp_delegado.save()

        self.emp_gestor = make_employee("gestor_test", "33333333-3", self.delegation, role_funcionario)
        self.emp_gestor.position = self.pos_gestor
        self.emp_gestor.save()

        self.client = Client()

    def test_reports_url_name(self):
        url = reverse('reports')
        self.assertEqual(url, '/reportes/')

    def test_reports_view_requires_login(self):
        response = self.client.get(reverse('reports'))
        self.assertIn(response.status_code, [302, 403])

    def test_reports_view_superuser_success(self):
        self.client.login(username="admin_test", password=DEMO_PASSWORD)
        response = self.client.get(reverse('reports') + f'?period={self.period.id}')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'portal/reports.html')
        self.assertIn('reporte_funcionarios', response.context)
        self.assertIn('ranking', response.context)

    def test_ranking_excludes_delegate(self):
        self.client.login(username="admin_test", password=DEMO_PASSWORD)
        response = self.client.get(reverse('reports') + f'?period={self.period.id}')
        self.assertEqual(response.status_code, 200)
        
        ranking = response.context['ranking']
        empleados_en_ranking = [r['employee'] for r in ranking]
        
        self.assertIn(self.emp_gestor, empleados_en_ranking)
        self.assertNotIn(self.emp_delegado, empleados_en_ranking)