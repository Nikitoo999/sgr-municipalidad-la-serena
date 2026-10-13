"""Pruebas de cierre (Parte 8): matriz de permisos parametrizada y alcance.

- La matriz recorre los 4 roles × 11 módulos × 5 acciones y, para cada
  combinación, comprueba ``has_permission`` contra la matriz declarada en
  ``sgr_core.roles.BASE_ROLES`` (fuente única de verdad), incluyendo el rol
  virtual del superusuario (todos los permisos).
- El test HTTP verifica que la acción "ver" responde 200 o 403 según la matriz
  en el listado real de cada módulo.
- El test de alcance usa datos en dos delegaciones y comprueba el filtrado por
  delegación activa y por rol (superadmin "Todas", coordinador según activa,
  delegado su delegación fija, funcionario solo registros propios).
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from operaciones.models import Attention, Neighbor
from portal.access import has_permission
from portal.tests.helpers import (
    DEMO_PASSWORD,
    TEST_STORAGES,
    ensure_roles,
    make_delegation,
    make_employee,
    make_user,
)
from sgr_core.models import AttentionSubtype, AttentionType, Role
from sgr_core.roles import ACTIONS, BASE_ROLES, MODULES

#: Clave de rol → usuario demo (el superadmin es rol virtual, sin Employee).
_ROLE_USERS = {
    "superadmin": "superadmin",
    "ROL02": "coordinador",
    "ROL03": "delegado",
    "ROL04": "funcionario",
}


def _expected_matrix():
    """Matriz esperada por rol: {(module, action), ...}.

    ROL01 (superadmin) tiene todos los permisos; los demás, los declarados en
    ``BASE_ROLES``.
    """
    all_combos = {(m, a) for m, _ in MODULES for a, _ in ACTIONS}
    expected = {}
    for spec in BASE_ROLES:
        key = "superadmin" if spec["code"] == "ROL01" else spec["code"]
        if key == "superadmin":
            expected[key] = set(all_combos)
            continue
        expected[key] = {
            (module, action)
            for module, actions in spec["permissions"].items()
            for action in actions
        }
    return expected


def _roles_by_code():
    return {role.code: role for role in Role.objects.all()}


@override_settings(STORAGES=TEST_STORAGES)
class PermissionMatrixParametrizedTests(TestCase):
    """Matriz de permisos 4×7×5, parametrizada con subTest."""

    @classmethod
    def setUpTestData(cls):
        ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02")

        cls.superadmin = make_user(
            "superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True,
        )
        coordinador = make_employee(
            "coordinador", "11.111.111-1", cls.d1, _roles_by_code()["ROL02"],
        )
        coordinador.authorized_delegations.set([cls.d1, cls.d2])
        cls.delegado = make_employee(
            "delegado", "11.111.112-2", cls.d1, _roles_by_code()["ROL03"],
        )
        cls.funcionario = make_employee(
            "funcionario", "11.111.113-3", cls.d1, _roles_by_code()["ROL04"],
        )

        cls.users = {
            "superadmin": cls.superadmin,
            "ROL02": coordinador.user,
            "ROL03": cls.delegado.user,
            "ROL04": cls.funcionario.user,
        }

    def test_matriz_permisos(self):
        expected = _expected_matrix()
        for role_key, username in _ROLE_USERS.items():
            user = self.users[role_key]
            for module, _ in MODULES:
                for action, _ in ACTIONS:
                    with self.subTest(role=role_key, module=module, action=action):
                        self.assertEqual(
                            has_permission(user, module, action),
                            (module, action) in expected[role_key],
                        )


@override_settings(STORAGES=TEST_STORAGES)
class PermissionMatrixHttpTests(TestCase):
    """La acción "ver" responde 200 (permitido) o 403 (denegado) según la matriz."""

    @classmethod
    def setUpTestData(cls):
        ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02")
        cls.superadmin = make_user(
            "superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True,
        )
        coordinador = make_employee(
            "coordinador", "11.111.111-1", cls.d1, _roles_by_code()["ROL02"],
        )
        coordinador.authorized_delegations.set([cls.d1, cls.d2])
        cls.delegado = make_employee("delegado", "11.111.112-2", cls.d1, _roles_by_code()["ROL03"])
        cls.funcionario = make_employee("funcionario", "11.111.113-3", cls.d1, _roles_by_code()["ROL04"])

    def test_listado_ver_200_o_403(self):
        expected = _expected_matrix()
        for role_key, username in _ROLE_USERS.items():
            self.client.login(username=username, password=DEMO_PASSWORD)
            for module, _ in MODULES:
                with self.subTest(role=role_key, module=module):
                    resp = self.client.get(reverse(module))
                    want = 200 if (module, "view") in expected[role_key] else 403
                    self.assertEqual(resp.status_code, want)
            self.client.logout()


@override_settings(STORAGES=TEST_STORAGES)
class DelegationScopeTests(TestCase):
    """Alcance por delegación con datos en dos delegaciones."""

    @classmethod
    def setUpTestData(cls):
        ensure_roles()
        roles = _roles_by_code()
        cls.d1 = make_delegation("Centro", "DEL01")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02")

        cls.superadmin = make_user(
            "superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True,
        )
        cls.coordinador = make_employee(
            "coordinador", "11.111.111-1", cls.d1, roles["ROL02"],
        )
        cls.coordinador.authorized_delegations.set([cls.d1, cls.d2])
        cls.delegado = make_employee("delegado", "11.111.112-2", cls.d1, roles["ROL03"])
        cls.funcionario = make_employee("funcionario", "11.111.113-3", cls.d1, roles["ROL04"])

        tipo = AttentionType.objects.create(code="TAT01", name="Social")
        sub = AttentionSubtype.objects.create(
            code="SAT01", name="Ayuda social", attention_type=tipo,
        )
        vecino = Neighbor.objects.create(identifier="11.111.111-1", full_name="María González")

        cls.att_d1_propia = Attention.objects.create(
            neighbor=vecino, delegation=cls.d1, attention_type=tipo,
            attention_subtype=sub, description="Atención propia en Centro.",
            responsible=cls.funcionario.user,
        )
        cls.att_d1_ajena = Attention.objects.create(
            neighbor=vecino, delegation=cls.d1, attention_type=tipo,
            attention_subtype=sub, description="Atención ajena en Centro.",
            responsible=cls.delegado.user,
        )
        cls.att_d2 = Attention.objects.create(
            neighbor=vecino, delegation=cls.d2, attention_type=tipo,
            attention_subtype=sub, description="Atención en Avenida del Mar.",
            responsible=cls.coordinador.user,
        )

    def _numbers(self, username):
        self.client.login(username=username, password=DEMO_PASSWORD)
        resp = self.client.get(reverse("attentions"))
        self.client.logout()
        self.assertEqual(resp.status_code, 200)
        return {row["cells"][0]["text"] for row in resp.context["rows"]}

    def test_superadmin_ve_todas(self):
        self.assertEqual(
            self._numbers("superadmin"),
            {self.att_d1_propia.number, self.att_d1_ajena.number, self.att_d2.number},
        )

    def test_coordinador_segun_delegacion_activa(self):
        # Por defecto la activa es la primera autorizada (DEL01).
        self.assertEqual(
            self._numbers("coordinador"),
            {self.att_d1_propia.number, self.att_d1_ajena.number},
        )
        # Al cambiar la activa a DEL02, solo se ven las de DEL02.
        self.client.login(username="coordinador", password=DEMO_PASSWORD)
        self.client.post(reverse("switch_delegation"), {"delegation": str(self.d2.pk)})
        resp = self.client.get(reverse("attentions"))
        self.client.logout()
        self.assertEqual(
            {row["cells"][0]["text"] for row in resp.context["rows"]},
            {self.att_d2.number},
        )

    def test_delegado_solo_su_delegacion(self):
        self.assertEqual(
            self._numbers("delegado"),
            {self.att_d1_propia.number, self.att_d1_ajena.number},
        )

    def test_funcionario_solo_sus_registros(self):
        self.assertEqual(self._numbers("funcionario"), {self.att_d1_propia.number})

