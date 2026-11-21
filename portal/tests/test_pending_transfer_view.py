from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from operaciones.models import Employee, Task
from portal.tests.helpers import (
    DEMO_PASSWORD, TEST_STORAGES, ensure_roles, make_delegation, make_employee,
)
from sgr_core.models import InstitutionalGoal, Period


@override_settings(STORAGES=TEST_STORAGES)
class PendingTransferViewTests(TestCase):
    """Pruebas para PendingTransferView (/pendientes-traspaso/): solo lectura, permisos y scoping."""

    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02")

        # Superadministrador: todos los permisos (rol virtual).
        from django.contrib.auth import get_user_model
        User = get_user_model()
        cls.superadmin = User.objects.create_user(
            username="supadmin_pt",
            password=DEMO_PASSWORD,
            is_superuser=True,
            is_staff=True,
        )

        # Coordinador (scope authorized) con d1 y d2 autorizadas; tiene tasks.view.
        cls.coord = make_employee(
            "coord_pt", "10.000.301-1", cls.d1, cls.roles["ROL02"],
        )
        cls.coord.authorized_delegations.set([cls.d1, cls.d2])

        # Delegado (scope own_delegation) en d1; tiene tasks.view.
        cls.delegado = make_employee(
            "delegado_pt", "10.000.302-2", cls.d1, cls.roles["ROL03"],
            first_name="Carmen", last_name="Soto",
        )
        cls.delegado.authorized_delegations.set([cls.d1])

        # Funcionaria (scope own_records) en d1; tiene tasks.view.
        cls.ana = make_employee(
            "ana_pt", "10.000.303-3", cls.d1, cls.roles["ROL04"],
            first_name="Ana", last_name="Pérez",
        )

        # Período CERRADO (candidato a traspaso) y período EN CURSO (no candidato).
        cls.periodo_cerrado = Period.objects.create(
            name="Trimestre Ago-Oct 2026",
            start_date=date(2026, 8, 1), end_date=date(2026, 10, 31),
            quarter=3, status="Cerrado",
        )
        cls.periodo_en_curso = Period.objects.create(
            name="Trimestre Nov-Dic 2026",
            start_date=date(2026, 11, 1), end_date=date(2026, 12, 31),
            quarter=4, status="En curso",
        )

        # Metas en períodos.
        cls.meta_cerrada_d1 = InstitutionalGoal.objects.create(
            name="Meta Cerrada d1", weight=100, period=cls.periodo_cerrado,
            delegation=cls.d1,
        )
        cls.meta_cerrada_d2 = InstitutionalGoal.objects.create(
            name="Meta Cerrada d2", weight=100, period=cls.periodo_cerrado,
            delegation=cls.d2,
        )
        cls.meta_en_curso_d1 = InstitutionalGoal.objects.create(
            name="Meta En Curso d1", weight=100, period=cls.periodo_en_curso,
            delegation=cls.d1,
        )

        # Tareas Pendiente y En Progreso en período CERRADO (deben aparecer).
        cls.t_pendiente_d1 = Task.objects.create(
            goal=cls.meta_cerrada_d1, title="Tarea Pendiente Cerrada d1",
            due_date=date(2026, 10, 15), status="Pendiente", assigned_to=cls.ana,
        )
        cls.t_enprogreso_d1 = Task.objects.create(
            goal=cls.meta_cerrada_d1, title="Tarea En Progreso Cerrada d1",
            due_date=date(2026, 10, 20), status="En Progreso", assigned_to=cls.ana,
        )
        cls.t_pendiente_d2 = Task.objects.create(
            goal=cls.meta_cerrada_d2, title="Tarea Pendiente Cerrada d2",
            due_date=date(2026, 10, 10), status="Pendiente", assigned_to=cls.delegado,
        )

        # Tarea Completada en período CERRADO (NO debe aparecer).
        cls.t_completada = Task.objects.create(
            goal=cls.meta_cerrada_d1, title="Tarea Completada Cerrada",
            due_date=date(2026, 10, 5), status="Completada", assigned_to=cls.ana,
        )

        # Tarea Pendiente en período EN CURSO (NO debe aparecer).
        cls.t_en_curso = Task.objects.create(
            goal=cls.meta_en_curso_d1, title="Tarea Pendiente En Curso",
            due_date=date(2026, 12, 15), status="Pendiente", assigned_to=cls.ana,
        )

        # Tarea soft-deleted en período CERRADO (NO debe aparecer).
        cls.t_borrada = Task.objects.create(
            goal=cls.meta_cerrada_d1, title="Tarea Borrada Cerrada",
            due_date=date(2026, 10, 1), status="Pendiente", assigned_to=cls.ana,
        )
        cls.t_borrada.deleted_at = date(2026, 11, 1)
        cls.t_borrada.save()

    def login(self, username="supadmin_pt"):
        self.client.login(username=username, password=DEMO_PASSWORD)

    def set_active(self, delegation):
        from portal.access import ACTIVE_DELEGATION_KEY, ALL_DELEGATIONS
        self.client.session[ACTIVE_DELEGATION_KEY] = (
            ALL_DELEGATIONS if delegation is None else str(delegation.pk)
        )
        self.client.session.save()

    def _nombres_en_contexto(self, resp):
        return {item.title for item in resp.context.get("pending_tasks", [])}

    # --- acceso ---------------------------------------------------------
    def test_con_permiso_tasks_view_responde_200(self):
        self.login()
        self.set_active(self.d1)
        resp = self.client.get(reverse("pending_transfer"))
        self.assertEqual(resp.status_code, 200)

    def test_sin_permiso_tasks_view_es_403(self):
        # Usuario autenticado sin Employee -> sin rol -> sin permisos.
        from django.contrib.auth import get_user_model
        User = get_user_model()
        sin_emp = User.objects.create_user(
            username="sin_emp_pt", password=DEMO_PASSWORD,
        )
        self.client.login(username="sin_emp_pt", password=DEMO_PASSWORD)
        self.set_active(self.d1)
        resp = self.client.get(reverse("pending_transfer"))
        self.assertEqual(resp.status_code, 403)

    # --- scoping --------------------------------------------------------
    def test_superadmin_ve_todas_las_delegaciones(self):
        self.login()
        self.set_active(None)  # ALL_DELEGATIONS
        resp = self.client.get(reverse("pending_transfer"))
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertIn("Tarea Pendiente Cerrada d1", nombres)
        self.assertIn("Tarea Pendiente Cerrada d2", nombres)

    def test_coordinador_ve_solo_delegacion_activa(self):
        self.login("coord_pt")
        self.set_active(self.d1)
        resp = self.client.get(reverse("pending_transfer"))
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertIn("Tarea Pendiente Cerrada d1", nombres)
        self.assertNotIn("Tarea Pendiente Cerrada d2", nombres)

    def test_funcionario_own_records_ve_solo_sus_tareas(self):
        self.login("ana_pt")
        self.set_active(self.d1)
        resp = self.client.get(reverse("pending_transfer"))
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertIn("Tarea Pendiente Cerrada d1", nombres)
        self.assertNotIn("Tarea Pendiente Cerrada d2", nombres)

    # --- exclusiones ----------------------------------------------------
    def test_tarea_completada_excluida(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("pending_transfer"))
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertNotIn("Tarea Completada Cerrada", nombres)

    def test_tarea_soft_deleted_excluida(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("pending_transfer"))
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertNotIn("Tarea Borrada Cerrada", nombres)

    def test_periodo_en_curso_excluido(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("pending_transfer"))
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertNotIn("Tarea Pendiente En Curso", nombres)

    def test_periodo_cerrado_incluido(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("pending_transfer"))
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertIn("Tarea Pendiente Cerrada d1", nombres)
        self.assertIn("Tarea En Progreso Cerrada d1", nombres)

    # --- resumen --------------------------------------------------------
    def test_conteo_resumen_coherente(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("pending_transfer"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_pendientes"], 3)
        self.assertEqual(resp.context["pendientes_count"], 2)
        self.assertEqual(resp.context["en_progreso_count"], 1)