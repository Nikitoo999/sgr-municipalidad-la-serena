from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from operaciones.models import Employee, Task
from portal.tests.helpers import (
    DEMO_PASSWORD, TEST_STORAGES, ensure_roles, make_delegation, make_employee,
)
from sgr_core.models import InstitutionalGoal, Period


@override_settings(STORAGES=TEST_STORAGES)
class PendingTransferExecuteViewTests(TestCase):
    """Pruebas para PendingTransferExecuteView (/pendientes-traspaso/<pk>/traspasar/): escritura segura."""

    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02")

        # Superadministrador: todos los permisos (rol virtual).
        from django.contrib.auth import get_user_model
        User = get_user_model()
        cls.superadmin = User.objects.create_user(
            username="supadmin_pte",
            password=DEMO_PASSWORD,
            is_superuser=True,
            is_staff=True,
        )

        # Delegado (scope own_delegation) en d1; tiene tasks.edit.
        cls.delegado = make_employee(
            "delegado_pte", "10.000.401-1", cls.d1, cls.roles["ROL03"],
            first_name="Carmen", last_name="Soto",
        )
        cls.delegado.authorized_delegations.set([cls.d1])

        # Coordinador (scope authorized) con d1 y d2 autorizadas; tiene tasks.view pero NO tasks.edit.
        cls.coord = make_employee(
            "coord_pte", "10.000.402-2", cls.d1, cls.roles["ROL02"],
        )
        cls.coord.authorized_delegations.set([cls.d1, cls.d2])

        # Funcionaria (scope own_records) en d1; tiene tasks.view pero NO tasks.edit.
        cls.ana = make_employee(
            "ana_pte", "10.000.403-3", cls.d1, cls.roles["ROL04"],
            first_name="Ana", last_name="Pérez",
        )

        # Período CERRADO y período EN CURSO en d1 y d2.
        cls.periodo_cerrado_d1 = Period.objects.create(
            name="Trimestre Ago-Oct 2026",
            start_date=date(2026, 8, 1), end_date=date(2026, 10, 31),
            quarter=3, status="Cerrado",
        )
        cls.periodo_en_curso_d1 = Period.objects.create(
            name="Trimestre Nov-Dic 2026",
            start_date=date(2026, 11, 1), end_date=date(2026, 12, 31),
            quarter=4, status="En curso",
        )
        cls.periodo_en_curso_d2 = Period.objects.create(
            name="Trimestre Nov-Dic 2026 d2",
            start_date=date(2026, 11, 1), end_date=date(2026, 12, 31),
            quarter=4, status="En curso",
        )

        # Metas en períodos EN CURSO.
        cls.meta_destino_d1 = InstitutionalGoal.objects.create(
            name="Meta Destino d1", weight=100, period=cls.periodo_en_curso_d1,
            delegation=cls.d1,
        )
        cls.meta_destino_d2 = InstitutionalGoal.objects.create(
            name="Meta Destino d2", weight=100, period=cls.periodo_en_curso_d2,
            delegation=cls.d2,
        )

        # Meta CERRADA en d1 (origen de tareas).
        cls.meta_cerrada_d1 = InstitutionalGoal.objects.create(
            name="Meta Cerrada d1", weight=100, period=cls.periodo_cerrado_d1,
            delegation=cls.d1,
        )

        # Tarea origen Pendiente en meta cerrada de d1, asignada a ana.
        cls.t_origen = Task.objects.create(
            goal=cls.meta_cerrada_d1, title="Tarea Única para Traspasar Delegado",
            due_date=date(2026, 10, 15), status="Pendiente", assigned_to=cls.ana,
        )

    def login(self, username="delegado_pte"):
        self.client.login(username=username, password=DEMO_PASSWORD)

    def set_active(self, delegation):
        from portal.access import ACTIVE_DELEGATION_KEY, ALL_DELEGATIONS
        self.client.session[ACTIVE_DELEGATION_KEY] = (
            ALL_DELEGATIONS if delegation is None else str(delegation.pk)
        )
        self.client.session.save()

    # --- éxito ----------------------------------------------------------
    def test_traspaso_exitoso_con_permiso(self):
        self.login()
        self.set_active(self.d1)
        resp = self.client.post(
            reverse("pending_transfer_execute", args=[self.t_origen.pk]),
            {"goal_id": self.meta_destino_d1.pk},
        )
        self.assertEqual(resp.status_code, 302)
        # La tarea origen sigue intacta
        self.t_origen.refresh_from_db()
        self.assertEqual(self.t_origen.status, "Pendiente")
        self.assertEqual(self.t_origen.goal, self.meta_cerrada_d1)
        # Nueva tarea creada en meta destino
        nueva = Task.objects.filter(
            goal=self.meta_destino_d1, title="Tarea Única para Traspasar Delegado",
            deleted_at__isnull=True,
        ).exclude(pk=self.t_origen.pk)
        self.assertTrue(nueva.exists())
        nueva = nueva.first()
        self.assertEqual(nueva.status, "Pendiente")
        self.assertEqual(nueva.assigned_to, self.ana)
        # due_date ajustado al final del período destino (2026-10-15 está ANTES del inicio
        # del período destino 2026-11-01, así que se usa period_end = 2026-12-31)
        self.assertEqual(nueva.due_date, date(2026, 12, 31))

    # --- permisos -------------------------------------------------------
    def test_traspaso_sin_permiso_edit_es_403(self):
        # Coordinador solo tiene tasks.view, no tasks.edit.
        self.login("coord_pte")
        self.set_active(self.d1)
        resp = self.client.post(
            reverse("pending_transfer_execute", args=[self.t_origen.pk]),
            {"goal_id": self.meta_destino_d1.pk},
        )
        self.assertEqual(resp.status_code, 403)

    def test_traspaso_funcionario_sin_edit_es_403(self):
        # Funcionaria own_records solo tiene tasks.view y tasks.create, no edit.
        self.login("ana_pte")
        self.set_active(self.d1)
        resp = self.client.post(
            reverse("pending_transfer_execute", args=[self.t_origen.pk]),
            {"goal_id": self.meta_destino_d1.pk},
        )
        self.assertEqual(resp.status_code, 403)

    def test_traspaso_usuario_sin_employee_es_403(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        sin_emp = User.objects.create_user(
            username="sin_emp_pte", password=DEMO_PASSWORD,
        )
        self.client.login(username="sin_emp_pte", password=DEMO_PASSWORD)
        self.set_active(self.d1)
        resp = self.client.post(
            reverse("pending_transfer_execute", args=[self.t_origen.pk]),
            {"goal_id": self.meta_destino_d1.pk},
        )
        self.assertEqual(resp.status_code, 403)

    # --- alcance y 404 --------------------------------------------------
    def test_traspaso_tarea_inexistente_es_404(self):
        self.login()
        self.set_active(self.d1)
        resp = self.client.post(
            reverse("pending_transfer_execute", args=[999999]),
            {"goal_id": self.meta_destino_d1.pk},
        )
        self.assertEqual(resp.status_code, 404)

    def test_traspaso_tarea_soft_deleted_es_404(self):
        # Marcar t_origen como soft-deleted
        self.t_origen.deleted_at = date(2026, 11, 1)
        self.t_origen.save()
        self.login()
        self.set_active(self.d1)
        resp = self.client.post(
            reverse("pending_transfer_execute", args=[self.t_origen.pk]),
            {"goal_id": self.meta_destino_d1.pk},
        )
        self.assertEqual(resp.status_code, 404)

    # --- validaciones de meta destino -----------------------------------
    def test_traspaso_meta_destino_no_en_curso_es_error(self):
        # Meta destino en período cerrado no es válida como destino.
        self.login()
        self.set_active(self.d1)
        resp = self.client.post(
            reverse("pending_transfer_execute", args=[self.t_origen.pk]),
            {"goal_id": self.meta_cerrada_d1.pk},
        )
        self.assertEqual(resp.status_code, 302)
        # No se crea duplicado: solo existe la tarea origen en meta_cerrada_d1
        self.assertEqual(
            Task.objects.filter(goal=self.meta_cerrada_d1, title="Tarea Única para Traspasar Delegado",
                               deleted_at__isnull=True).count(), 1
        )

    def test_traspaso_meta_destino_otra_delegacion_es_error(self):
        # Meta destino en d2, delegación activa d1 -> error.
        self.login()
        self.set_active(self.d1)
        resp = self.client.post(
            reverse("pending_transfer_execute", args=[self.t_origen.pk]),
            {"goal_id": self.meta_destino_d2.pk},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            Task.objects.filter(goal=self.meta_destino_d2, deleted_at__isnull=True).count(),
            0
        )

    def test_traspaso_goal_id_invalido_es_error(self):
        self.login()
        self.set_active(self.d1)
        resp = self.client.post(
            reverse("pending_transfer_execute", args=[self.t_origen.pk]),
            {"goal_id": "abc"},
        )
        self.assertEqual(resp.status_code, 302)

    def test_traspaso_goal_id_inexistente_es_error(self):
        self.login()
        self.set_active(self.d1)
        resp = self.client.post(
            reverse("pending_transfer_execute", args=[self.t_origen.pk]),
            {"goal_id": 999999},
        )
        self.assertEqual(resp.status_code, 302)

    # --- duplicados -----------------------------------------------------
    def test_traspaso_duplicado_no_crea_segunda_tarea(self):
        # Crear una tarea con el mismo title en meta destino d1 primero.
        Task.objects.create(
            goal=self.meta_destino_d1, title="Tarea Única para Traspasar Delegado",
            due_date=date(2026, 12, 15), status="Pendiente", assigned_to=self.ana,
        )
        self.login()
        self.set_active(self.d1)
        resp = self.client.post(
            reverse("pending_transfer_execute", args=[self.t_origen.pk]),
            {"goal_id": self.meta_destino_d1.pk},
        )
        self.assertEqual(resp.status_code, 302)
        # No se creó una segunda tarea con ese title en esa meta
        count = Task.objects.filter(
            goal=self.meta_destino_d1, title="Tarea Única para Traspasar Delegado",
            deleted_at__isnull=True,
        ).count()
        self.assertEqual(count, 1)  # solo la creada arriba, no se duplicó

    # --- rollback ante error -------------------------------------------
    def test_rollback_ante_error_no_deja_tarea_parcial(self):
        # Simular error de base de datos: forzar una excepción al guardar
        # haciendo que la meta destino sea None (fuerza IntegrityError al crear Task sin goal válido)
        # En su lugar, usamos un mock sobre Task.objects.create para lanzar excepción.
        from unittest.mock import patch
        self.login()
        self.set_active(self.d1)
        with patch.object(Task.objects, 'create', side_effect=Exception("Error simulado de BD")):
            resp = self.client.post(
                reverse("pending_transfer_execute", args=[self.t_origen.pk]),
                {"goal_id": self.meta_destino_d1.pk},
            )
        self.assertEqual(resp.status_code, 302)
        # No se creó ninguna tarea nueva en meta destino
        self.assertEqual(
            Task.objects.filter(goal=self.meta_destino_d1, deleted_at__isnull=True).count(),
            0  # no se creó ninguna
        )
