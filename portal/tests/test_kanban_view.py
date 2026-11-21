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

    def test_con_permiso_tasks_view_responde_200(self):
        self.login()
        self.set_active(self.d1)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 200)

    def test_sin_permiso_tasks_view_es_403(self):
        # Usuario autenticado pero sin Employee -> get_role es None -> sin permisos.
        sin_emp = User.objects.create_user(
            username="sin_emp_kanban", password=DEMO_PASSWORD,
        )
        self.client.login(username="sin_emp_kanban", password=DEMO_PASSWORD)
        self.set_active(self.d1)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 403)

    # --- scoping --------------------------------------------------------
    def test_superadmin_ve_todas_las_delegaciones(self):
        self.login()
        self.set_active(None)  # ALL_DELEGATIONS
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 200)
        codigos = self._codigos_columnas(resp)
        self.assertIn(self.t1.code, codigos)
        self.assertIn(self.t4.code, codigos)
        self.assertNotIn(self.t5.code, codigos)  # soft-deleted excluida

    def test_coordinador_ve_solo_delegacion_activa(self):
        self.login("coord_kanban")
        self.set_active(self.d1)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 200)
        codigos = self._codigos_columnas(resp)
        self.assertIn(self.t1.code, codigos)
        self.assertNotIn(self.t4.code, codigos)  # d2 no visible desde d1

    def test_funcionario_own_records_ve_solo_sus_tareas(self):
        self.login("ana_kanban")
        self.set_active(self.d1)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 200)
        codigos = self._codigos_columnas(resp)
        self.assertIn(self.t1.code, codigos)  # ana es assigned_to
        self.assertNotIn(self.t3.code, codigos)  # no asignada a ana
        self.assertNotIn(self.t4.code, codigos)  # d2 / de luis

    def test_tareas_soft_deleted_excluidas(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 200)
        codigos = self._codigos_columnas(resp)
        self.assertNotIn(self.t5.code, codigos)

    # --- agrupación por estado ------------------------------------------
    def test_agrupa_por_estado(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 200)
        columnas = resp.context["columnas"]
        estados = {
            estado: [item["tarea"].code for item in tareas]
            for estado, tareas in columnas.items()
        }
        self.assertIn(self.t1.code, estados["Pendiente"])
        self.assertIn(self.t2.code, estados["En Progreso"])
        self.assertIn(self.t3.code, estados["Completada"])

    # --- filtros GET ----------------------------------------------------
    def test_filtrar_por_goal(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("kanban_tasks"), {"goal": self.g2.pk})
        self.assertEqual(resp.status_code, 200)
        codigos = self._codigos_columnas(resp)
        self.assertIn(self.t4.code, codigos)  # meta g2
        self.assertNotIn(self.t1.code, codigos)  # meta g1

    def test_filtrar_por_assigned_to_id(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(
            reverse("kanban_tasks"), {"assigned_to": self.ana.pk}
        )
        self.assertEqual(resp.status_code, 200)
        codigos = self._codigos_columnas(resp)
        self.assertIn(self.t1.code, codigos)  # assigned_to = ana
        self.assertIn(self.t2.code, codigos)
        self.assertNotIn(self.t3.code, codigos)  # assigned_to = None
        self.assertNotIn(self.t4.code, codigos)  # assigned_to = luis

    def test_filtrar_por_unassigned(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(
            reverse("kanban_tasks"), {"assigned_to": "unassigned"}
        )
        self.assertEqual(resp.status_code, 200)
        codigos = self._codigos_columnas(resp)
        self.assertIn(self.t3.code, codigos)  # assigned_to__isnull=True

    def test_filtrar_por_assigned_to_inexistente_devuelve_vacio(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(
            reverse("kanban_tasks"), {"assigned_to": 999999}
        )
        self.assertEqual(resp.status_code, 200)
        codigos = self._codigos_columnas(resp)
        self.assertEqual(codigos, set())

    # --- tolerancia a valores inválidos --------------------------------
    def test_valor_goal_invalido_no_rompe(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("kanban_tasks"), {"goal": "abc"})
        self.assertEqual(resp.status_code, 200)

    def test_valor_assigned_to_invalido_no_rompe(self):
        self.login()
        self.set_active(None)
        resp = self.client.get(reverse("kanban_tasks"), {"assigned_to": "basura"})
        self.assertEqual(resp.status_code, 200)

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

    def test_cambiar_estado_exitoso_con_permiso(self):
        resp = self._post_cambiar_estado(self.t1.pk, "Completada", delegation=None)
        self.assertEqual(resp.status_code, 302)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, "Completada")

    def test_cambiar_estado_sin_permiso_es_403(self):
        # Coordinador solo tiene tasks.view, no tasks.edit.
        resp = self._post_cambiar_estado(self.t1.pk, "Completada",
                                         username="coord_kanban", delegation=None)
        self.assertEqual(resp.status_code, 403)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, "Pendiente")

    def test_cambiar_estado_funcionario_sin_permiso_es_403(self):
        # Funcionario own_records solo tiene tasks.view y tasks.create, no edit.
        resp = self._post_cambiar_estado(self.t1.pk, "Completada",
                                         username="ana_kanban", delegation=self.d1)
        self.assertEqual(resp.status_code, 403)

    def test_cambiar_estado_exitoso_con_delegado_en_su_delegacion(self):
        # Delegado con tasks.edit puede editar tareas de su delegación activa.
        resp = self._post_cambiar_estado(self.t1.pk, "En Progreso",
                                         username="delegado_kanban", delegation=self.d1)
        self.assertEqual(resp.status_code, 302)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, "En Progreso")

    def test_cambiar_estado_fuera_de_alcance_es_404(self):
        # Delegado con delegación activa d1 no puede editar tarea de d2.
        resp = self._post_cambiar_estado(self.t4.pk, "Completada",
                                         username="delegado_kanban", delegation=self.d1)
        self.assertEqual(resp.status_code, 404)
        self.t4.refresh_from_db()
        self.assertEqual(self.t4.status, "Pendiente")

    def test_cambiar_estado_tarea_soft_deleted_es_404(self):
        self.set_active(None)
        resp = self._post_cambiar_estado(self.t5.pk, "Completada")
        self.assertEqual(resp.status_code, 404)
        self.t5.refresh_from_db()
        self.assertEqual(self.t5.status, "Pendiente")

    def test_estado_invalido_no_altera_bd(self):
        self.set_active(None)
        resp = self._post_cambiar_estado(self.t1.pk, "EstadoInexistente")
        self.assertEqual(resp.status_code, 302)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, "Pendiente")

    def test_redireccion_preserva_filtros_goal_y_assigned_to(self):
        self.login()
        self.set_active(None)
        resp = self.client.post(
            reverse("kanban_task_status_change", args=[self.t1.pk]),
            {"status": "Completada", "goal": self.g1.pk, "assigned_to": self.ana.pk},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"goal={self.g1.pk}", resp.url)
        self.assertIn(f"assigned_to={self.ana.pk}", resp.url)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, "Completada")

    def test_own_records_solo_sus_propias_tareas(self):
        # Ana (own_records, d1) intenta editar t3 (sin asignar, d1): sin permiso edit → 403.
        self.set_active(self.d1)
        resp = self._post_cambiar_estado(self.t3.pk, "En Progreso", username="ana_kanban")
        self.assertEqual(resp.status_code, 403)

    # --- enlace de navegación --------------------------------------------
    def test_usuario_con_tasks_view_ve_enlace_kanban(self):
        self.login()
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"/kanban-tareas/", resp.content)

    def test_usuario_sin_tasks_view_no_ve_enlace_kanban(self):
        # Usuario autenticado sin Employee -> sin rol -> sin tareas.view.
        sin_emp = User.objects.create_user(
            username="sin_emp_nav", password=DEMO_PASSWORD,
        )
        self.client.login(username="sin_emp_nav", password=DEMO_PASSWORD)
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"/kanban-tareas/", resp.content)

    def test_enlace_kanban_activo_cuando_esta_en_kanban(self):
        self.login()
        resp = self.client.get(reverse("kanban_tasks"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'href="/kanban-tareas/" aria-current="page"', resp.content)

    def test_enlace_kanban_no_activo_fuera_de_kanban(self):
        self.login()
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'href="/kanban-tareas/"', resp.content)
        self.assertNotIn(
            b'href="/kanban-tareas/" aria-current="page"', resp.content
        )

