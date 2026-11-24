from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from operaciones.models import Employee
from portal.tests.helpers import (
    DEMO_PASSWORD, TEST_STORAGES, ensure_roles, make_delegation, make_employee,
)
from sgr_core.models import Delegation


@override_settings(STORAGES=TEST_STORAGES)
class OrganigramViewTests(TestCase):
    """Pruebas para OrganigramView (/organigrama/): solo lectura, permisos y scoping."""

    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02")

        # Superadministrador: todos los permisos (rol virtual).
        from django.contrib.auth import get_user_model
        User = get_user_model()
        cls.superadmin = User.objects.create_user(
            username="supadmin_org",
            password=DEMO_PASSWORD,
            is_superuser=True,
            is_staff=True,
        )

        # Coordinador (scope authorized) con d1 y d2 autorizadas; tiene users.view.
        cls.coord = make_employee(
            "coord_org", "10.000.201-1", cls.d1, cls.roles["ROL02"],
        )
        cls.coord.authorized_delegations.set([cls.d1, cls.d2])

        # Delegado (scope own_delegation) en d1; tiene users.view.
        cls.delegado = make_employee(
            "delegado_org", "10.000.202-2", cls.d1, cls.roles["ROL03"],
            first_name="Carmen", last_name="Soto",
        )
        cls.delegado.authorized_delegations.set([cls.d1])

        # Funcionaria (scope own_records) en d1; NO tiene users.view.
        cls.ana = make_employee(
            "ana_org", "10.000.203-3", cls.d1, cls.roles["ROL04"],
            first_name="Ana", last_name="Pérez",
        )

        # Empleados en d1 y d2 para poblar el organigrama.
        cls.emp_d1_1 = make_employee(
            "emp_d1_1", "10.000.210-1", cls.d1, cls.roles["ROL04"],
            first_name="Luis", last_name="Rojas",
        )
        cls.emp_d1_2 = make_employee(
            "emp_d1_2", "10.000.211-2", cls.d1, cls.roles["ROL04"],
            first_name="María", last_name="González",
        )
        cls.emp_d2 = make_employee(
            "emp_d2", "10.000.212-3", cls.d2, cls.roles["ROL04"],
            first_name="Pedro", last_name="López",
        )

    def login(self, username="supadmin_org"):
        self.client.login(username=username, password=DEMO_PASSWORD)

    def set_active(self, delegation):
        from portal.access import ACTIVE_DELEGATION_KEY, ALL_DELEGATIONS
        self.client.session[ACTIVE_DELEGATION_KEY] = (
            ALL_DELEGATIONS if delegation is None else str(delegation.pk)
        )
        self.client.session.save()

    # --- acceso ---------------------------------------------------------
    def test_con_permiso_users_view_responde_200(self):
        self.login()
        self.set_active(self.d1)
        resp = self.client.get(reverse("organigrama"))
        self.assertEqual(resp.status_code, 200)

    def test_sin_permiso_users_view_es_403(self):
        # Funcionaria (own_records) no tiene users.view.
        self.login("ana_org")
        self.set_active(self.d1)
        resp = self.client.get(reverse("organigrama"))
        self.assertEqual(resp.status_code, 403)

    def test_usuario_sin_employee_es_403(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        sin_emp = User.objects.create_user(
            username="sin_emp_org", password=DEMO_PASSWORD,
        )
        self.client.login(username="sin_emp_org", password=DEMO_PASSWORD)
        self.set_active(self.d1)
        resp = self.client.get(reverse("organigrama"))
        self.assertEqual(resp.status_code, 403)

    # --- scoping --------------------------------------------------------
    def _nombres_en_contexto(self, resp):
        """Devuelve el conjunto de full_name de empleados en el contexto."""
        nombres = set()
        org = resp.context.get("organigrama", {})
        for _delegacion, posiciones in org.items():
            for _pos, empleados in posiciones.items():
                for item in empleados:
                    nombres.add(item["full_name"])
        return nombres

    def test_superadmin_ve_todas_las_delegaciones(self):
        self.login()
        self.set_active(None)  # ALL_DELEGATIONS
        resp = self.client.get(reverse("organigrama"))
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertIn(self.emp_d1_1.full_name, nombres)
        self.assertIn(self.emp_d1_2.full_name, nombres)
        self.assertIn(self.emp_d2.full_name, nombres)

    def test_coordinador_ve_solo_delegaciones_autorizadas(self):
        self.login("coord_org")
        self.set_active(self.d1)
        resp = self.client.get(reverse("organigrama"))
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertIn(self.emp_d1_1.full_name, nombres)
        self.assertIn(self.emp_d1_2.full_name, nombres)
        # d2 no es la delegación activa, no debe aparecer por scoping activo.
        self.assertNotIn(self.emp_d2.full_name, nombres)

    def test_delegado_ve_su_delegacion(self):
        self.login("delegado_org")
        self.set_active(self.d1)
        resp = self.client.get(reverse("organigrama"))
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertIn(self.emp_d1_1.full_name, nombres)
        self.assertIn(self.emp_d1_2.full_name, nombres)
        self.assertNotIn(self.emp_d2.full_name, nombres)

    def test_own_records_no_tiene_permiso_users_view(self):
        # Funcionaria own_records no tiene users.view, por tanto 403.
        self.login("ana_org")
        self.set_active(self.d1)
        resp = self.client.get(reverse("organigrama"))
        self.assertEqual(resp.status_code, 403)

    # --- soft-delete ----------------------------------------------------
    def test_empleado_soft_deleted_excluido(self):
        self.login()
        self.set_active(None)  # ALL_DELEGATIONS
        # Marcar emp_d2 como soft-deleted.
        self.emp_d2.deleted_at = date(2026, 11, 1)
        self.emp_d2.save()
        resp = self.client.get(reverse("organigrama"))
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertIn(self.emp_d1_1.full_name, nombres)
        self.assertIn(self.emp_d1_2.full_name, nombres)
        self.assertNotIn(self.emp_d2.full_name, nombres)

    # --- filtro delegation con ALL --------------------------------------
    def test_filtro_delegation_con_all(self):
        self.login()
        self.set_active(None)  # ALL_DELEGATIONS
        resp = self.client.get(
            reverse("organigrama"), {"delegation": self.d2.pk}
        )
        self.assertEqual(resp.status_code, 200)
        nombres = self._nombres_en_contexto(resp)
        self.assertIn(self.emp_d2.full_name, nombres)
        self.assertNotIn(self.emp_d1_1.full_name, nombres)
        self.assertNotIn(self.emp_d1_2.full_name, nombres)

    def test_filtro_delegation_invalido_no_rompe(self):
        self.login()
        self.set_active(None)  # ALL_DELEGATIONS
        resp = self.client.get(
            reverse("organigrama"), {"delegation": "abc"}
        )
        self.assertEqual(resp.status_code, 200)

    # --- enlace de navegación --------------------------------------------
    def test_usuario_con_users_view_ve_enlace_organigrama(self):
        self.login()
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"/organigrama/", resp.content)

    def test_usuario_sin_users_view_no_ve_enlace_organigrama(self):
        # Funcionaria (own_records) no tiene users.view.
        self.login("ana_org")
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        # El organigrama de funcionarios no aparece (el de organizaciones,
        # /organizaciones/organigrama/, sí le corresponde: solo consulta).
        self.assertNotIn(b'href="/organigrama/"', resp.content)

    def test_enlace_organigrama_activo_cuando_esta_en_organigrama(self):
        self.login()
        resp = self.client.get(reverse("organigrama"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'href="/organigrama/" aria-current="page"', resp.content)

    def test_enlace_organigrama_no_activo_fuera_de_organigrama(self):
        self.login()
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'href="/organigrama/"', resp.content)
        self.assertNotIn(
            b'href="/organigrama/" aria-current="page"', resp.content
        )