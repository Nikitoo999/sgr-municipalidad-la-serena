from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from operaciones.models import Task
from portal.access import ACTIVE_DELEGATION_KEY, ALL_DELEGATIONS
from portal.tests.helpers import (
    DEMO_PASSWORD, TEST_STORAGES, ensure_roles, make_delegation, make_employee,
)
from sgr_core.models import InstitutionalGoal, Period

User = get_user_model()


@override_settings(STORAGES=TEST_STORAGES)
class KanbanViewTests(TestCase):
    """Pruebas para KanbanView (/kanban-tareas/): solo lectura, scopes y filtros GET."""

    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02")
        periodo = Period.objects.create(
            name="Trimestre Oct-Dic 2026",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 12, 31),
            quarter=4,
        )
        cls.g1 = InstitutionalGoal.objects.create(
            name="Meta Centro", weight=100, period=periodo, delegation=cls.d1
        )
        cls.g2 = InstitutionalGoal.objects.create(
            name="Meta Av. del Mar", weight=100, period=periodo, delegation=cls.d2
        )
        # Superadministrador: todos los permisos (rol virtual).
        cls.superadmin = User.objects.create_user(
            username="supadmin_kanban",
            password=DEMO_PASSWORD,
            is_superuser=True,
            is_staff=True,
        )
        # Coordinador (scope authorized) con d1 y d2 autorizadas; tiene tasks.view.
        cls.coord = make_employee(
            "coord_kanban", "10.000.101-1", cls.d1, cls.roles["ROL02"],
        )
        cls.coord.authorized_delegations.set([cls.d1, cls.d2])
        # Funcionaria own_records en d1; tiene tasks.view.
        cls.ana = make_employee(
            "ana_kanban", "10.000.102-2", cls.d1, cls.roles["ROL04"],
            first_name="Ana", last_name="Pérez",
        )
        # Funcionario own_records en d2; tiene tasks.view.
        cls.luis = make_employee(
            "luis_kanban", "10.000.103-3", cls.d2, cls.roles["ROL04"],
            first_name="Luis", last_name="Rojas",
        )
        # Delegado en d1; tiene tasks.view, tasks.create y tasks.edit.
        cls.delegado = make_employee(
            "delegado_kanban", "10.000.104-4", cls.d1, cls.roles["ROL03"],
            first_name="Carmen", last_name="Soto",
        )
        cls.delegado.authorized_delegations.set([cls.d1])

        # Tareas en d1 (meta g1).
        cls.t1 = Task.objects.create(
            goal=cls.g1, title="Tarea Pendiente d1",
            due_date=date(2026, 12, 1), status="Pendiente", assigned_to=cls.ana,
        )
        cls.t2 = Task.objects.create(
            goal=cls.g1, title="Tarea En Progreso d1",
            due_date=date(2026, 12, 2), status="En Progreso", assigned_to=cls.ana,
        )
        cls.t3 = Task.objects.create(
            goal=cls.g1, title="Tarea Completada d1",
            due_date=date(2026, 12, 3), status="Completada", assigned_to=None,
        )
        # Tarea en d2 (meta g2).
        cls.t4 = Task.objects.create(
            goal=cls.g2, title="Tarea d2",
            due_date=date(2026, 12, 4), status="Pendiente", assigned_to=cls.luis,
        )
        # Tarea soft-deleted en d1: debe excluirse siempre.
        cls.t5 = Task.objects.create(
            goal=cls.g1, title="Tarea Borrada d1",
            due_date=date(2026, 12, 5), status="Pendiente", assigned_to=cls.ana,
        )
        cls.t5.deleted_at = timezone.now()
        cls.t5.save()

    def login(self, username="supadmin_kanban"):
        self.client.login(username=username, password=DEMO_PASSWORD)

    def set_active(self, delegation):
        """Establece la delegación activa en la sesión del test client."""
        self.client.session[ACTIVE_DELEGATION_KEY] = (
            ALL_DELEGATIONS if delegation is None else str(delegation.pk)
        )
        self.client.session.save()

    def _codigos_columnas(self, resp):
        columnas = resp.context["columnas"]
        return {
            item["tarea"].code
            for estado, tareas in columnas.items()
            for item in tareas
        }

    # --- acceso ---------------------------------------------------------
    def test_sin_sesion_redirige_a_login(self):
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_kanban_redirige_a_tubos_con_permiso(self):
        self.login()
        self.set_active(self.d1)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)

    def test_kanban_redirige_a_tubos_sin_empleado(self):
        # Usuario autenticado pero sin Employee -> get_role es None.
        # KanbanRedirectView solo tiene LoginRequiredMixin, así que redirige (no 403).
        sin_emp = User.objects.create_user(
            username="sin_emp_kanban", password=DEMO_PASSWORD,
        )
        self.client.login(username="sin_emp_kanban", password=DEMO_PASSWORD)
        self.set_active(self.d1)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)

    # --- scoping (ya no aplica: kanban redirige, no muestra columnas) ---
    def test_superadmin_ve_redirect_a_tubos(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)

    def test_coordinador_ve_redirect_a_tubos(self):
        self.login("coord_kanban")
        self.set_active(self.d1)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)

    def test_funcionario_own_records_ve_redirect_a_tubos(self):
        self.login("ana_kanban")
        self.set_active(self.d1)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)

    def test_tareas_no_se_listan_en_kanban(self):
        """Ya no hay listado de tareas en kanban; todo va al tubo."""
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 302)

    # --- filtros GET (ya no aplican: kanban redirige) -------------------
    def test_filtrar_por_goal_redirige_a_tubos(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("kanban_tasks"), {"goal": self.g2.pk})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)

    def test_filtrar_por_assigned_to_redirige_a_tubos(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(
            reverse("kanban_tasks"), {"assigned_to": self.ana.pk}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)

    def test_filtrar_por_unassigned_redirige_a_tubos(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(
            reverse("kanban_tasks"), {"assigned_to": "unassigned"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)

    def test_filtrar_por_assigned_to_inexistente_redirige_a_tubos(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(
            reverse("kanban_tasks"), {"assigned_to": 999999}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)

    # --- tolerancia a valores inválidos (redirige igual) ----------------
    def test_valor_goal_invalido_redirige_a_tubos(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("kanban_tasks"), {"goal": "abc"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)

    def test_valor_assigned_to_invalido_redirige_a_tubos(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("kanban_tasks"), {"assigned_to": "basura"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)

    # --- cambio de estado (POST) ----------------------------------------
    def _post_cambiar_estado(self, task_id, status, username="supadmin_kanban",
                             delegation=None, **params):
        self.login(username)
        if delegation is not None:
            self.set_active(delegation)
        if params:
            return self.client.post(
                reverse("kanban_task_status_change", args=[task_id]),
                {"status": status, **params},
            )
        return self.client.post(
            reverse("kanban_task_status_change", args=[task_id]),
            {"status": status},
        )

    def test_cambiar_estado_redirige_a_tubos(self):
        """El cambio de estado de tarea ya no existe: redirige al tubo."""
        resp = self._post_cambiar_estado(self.t1.pk, "Completada", delegation=None)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)
        # La tarea NO se modifica (kanban fue reemplazado).
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, "Pendiente")

    def test_cambiar_estado_sin_permiso_redirige_a_tubos(self):
        # Coordinador solo tiene tasks.view, no tasks.edit.
        # KanbanTaskStatusChangeRedirectView tiene ModulePermissionMixin (tasks.edit),
        # así que coordinador recibe 403.
        resp = self._post_cambiar_estado(self.t1.pk, "Completada",
                                         username="coord_kanban", delegation=None)
        self.assertEqual(resp.status_code, 403)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, "Pendiente")

    def test_cambiar_estado_funcionario_sin_permiso_redirige_o_403(self):
        # Funcionario own_records solo tiene tasks.view y tasks.create, no edit.
        resp = self._post_cambiar_estado(self.t1.pk, "Completada",
                                         username="ana_kanban", delegation=self.d1)
        self.assertEqual(resp.status_code, 403)

    def test_cambiar_estado_delegado_redirige_a_tubos(self):
        # Delegado con tasks.edit: la vista de redirect tiene ModulePermissionMixin
        # y permite tasks.edit, así que redirige a tubos (no modifica la tarea).
        resp = self._post_cambiar_estado(self.t1.pk, "En Progreso",
                                         username="delegado_kanban", delegation=self.d1)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, "Pendiente")

    def test_cambiar_estado_fuera_de_alcance_redirige_a_tubos(self):
        # Delegado con delegación activa d1: la vista de redirect no valida
        # alcance de tarea, solo redirige a tubos.
        resp = self._post_cambiar_estado(self.t4.pk, "Completada",
                                         username="delegado_kanban", delegation=self.d1)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)
        self.t4.refresh_from_db()
        self.assertEqual(self.t4.status, "Pendiente")

    def test_cambiar_estado_tarea_soft_deleted_redirige_a_tubos(self):
        # La vista de redirect no consulta la tarea, solo redirige.
        self.set_active(None)
        resp = self._post_cambiar_estado(self.t5.pk, "Completada")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)
        self.t5.refresh_from_db()
        self.assertEqual(self.t5.status, "Pendiente")

    def test_estado_invalido_redirige_a_tubos(self):
        self.set_active(None)
        resp = self._post_cambiar_estado(self.t1.pk, "EstadoInexistente")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, "Pendiente")

    def test_redireccion_no_preserva_filtros(self):
        self.login()
        self.set_active(None)
        resp = self.client.post(
            reverse("kanban_task_status_change", args=[self.t1.pk]),
            {"status": "Completada", "goal": self.g1.pk, "assigned_to": self.ana.pk},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/cumplimiento/tubos/", resp.url)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, "Pendiente")

    def test_own_records_solo_sus_propias_tareas_403(self):
        # Ana (own_records, d1) intenta editar t3 (sin asignar, d1): sin permiso edit → 403.
        self.set_active(self.d1)
        resp = self._post_cambiar_estado(self.t3.pk, "En Progreso", username="ana_kanban")
        self.assertEqual(resp.status_code, 403)

    # --- enlace de navegación --------------------------------------------
    def test_usuario_con_tasks_view_ve_enlace_tubos(self):
        self.login()
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"/cumplimiento/tubos/", resp.content)
        self.assertNotIn(b"/kanban-tareas/", resp.content)

    def test_usuario_sin_tasks_view_no_ve_enlace_tubos(self):
        # Usuario autenticado sin Employee -> sin rol -> sin tareas.view.
        sin_emp = User.objects.create_user(
            username="sin_emp_nav", password=DEMO_PASSWORD,
        )
        self.client.login(username="sin_emp_nav", password=DEMO_PASSWORD)
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"/cumplimiento/tubos/", resp.content)
        self.assertNotIn(b"/kanban-tareas/", resp.content)

    def test_enlace_tubos_activo_cuando_esta_en_tubos(self):
        self.login()
        resp = self.client.get(reverse("tubes"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'href="/cumplimiento/tubos/" aria-current="page"', resp.content)

    def test_enlace_tubos_no_activo_fuera_de_tubos(self):
        self.login()
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'href="/cumplimiento/tubos/"', resp.content)
        self.assertNotIn(
            b'href="/cumplimiento/tubos/" aria-current="page"', resp.content
        )

