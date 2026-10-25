"""Pruebas de filtros declarados del motor CRUD (grilla de filtros).

Cubre:
- Claves reservadas rechazadas al registrar el módulo.
- Filtros aplicados al queryset con valores válidos.
- Valores GET no válidos (no están en opciones) se ignoran.
- Opciones ya acotadas por alcance de rol (users: rol + delegación).
- La paginación, filas por página y exportación conservan los filtros.
- Etiquetas de filtro activo se muestran y quitan su propio filtro.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from portal.tests.helpers import (
    DEMO_PASSWORD,
    TEST_STORAGES,
    ensure_roles,
    make_delegation,
    make_employee,
    make_user,
)
from portal.crud.config import FilterSpec, ModuleConfig, register_module
from sgr_core.models import Delegation, Role
from sgr_core.roles import ensure_base_roles


@override_settings(STORAGES=TEST_STORAGES)
class CrudFiltersTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02", color="#1D6FA5")

        cls.superuser = make_user(
            "superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True,
        )
        cls.coordinador = make_employee(
            "coordinador", "11.111.111-1", cls.d1, cls.roles["ROL02"],
        )
        cls.coordinador.authorized_delegations.set([cls.d1, cls.d2])
        cls.delegado = make_employee(
            "delegado", "11.111.112-2", cls.d1, cls.roles["ROL03"],
        )
        cls.funcionario = make_employee(
            "funcionario", "11.111.113-3", cls.d1, cls.roles["ROL04"],
        )

    def _login(self, username):
        self.client.logout()
        assert self.client.login(username=username, password=DEMO_PASSWORD)

    def _fltr_names(self, resp):
        return [item["key"] for item in resp.context["filters"]]

    def _row_texts(self, resp):
        return [row["cells"][0]["text"] for row in resp.context["rows"]]

    def _cell(self, resp, col_index):
        return [row["cells"][col_index]["text"] for row in resp.context["rows"]]

    def test_registro_rechaza_clave_reservada(self):
        config = ModuleConfig(
            module_key="probe_reserved", slug="probe-reservado",
            model=Delegation, form_class=None, list_title="Probe",
            singular_label="Probe",
            filters=(FilterSpec("q", "Búsqueda", "name"),),
        )
        with self.assertRaises(ValueError) as ctx:
            register_module(config)
        self.assertIn("q", str(ctx.exception))

    def test_registro_rechaza_clave_duplicada(self):
        config = ModuleConfig(
            module_key="probe_dup", slug="probe-dup",
            model=Delegation, form_class=None, list_title="Probe",
            singular_label="Probe",
            filters=(
                FilterSpec("x", "X", "name"),
                FilterSpec("x", "X otra", "code"),
            ),
        )
        with self.assertRaises(ValueError) as ctx:
            register_module(config)
        self.assertIn("x", str(ctx.exception))

    def test_users_filtros_declarados(self):
        self._login("superadmin")
        resp = self.client.get(reverse("users"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._fltr_names(resp), ["rol", "delegacion"])

    def test_users_opciones_rol_superadmin_ve_todos(self):
        self._login("superadmin")
        resp = self.client.get(reverse("users"))
        keys = [o["value"] for o in resp.context["filters"][0]["options"]]
        self.assertIn(str(self.roles["ROL01"].pk), keys)
        self.assertIn(str(self.roles["ROL02"].pk), keys)
        self.assertIn(str(self.roles["ROL03"].pk), keys)
        self.assertIn(str(self.roles["ROL04"].pk), keys)

    def test_users_opciones_rol_coordinador_ve_inferiores(self):
        self._login("coordinador")
        resp = self.client.get(reverse("users"))
        keys = [o["value"] for o in resp.context["filters"][0]["options"]]
        self.assertIn(str(self.roles["ROL03"].pk), keys)
        self.assertIn(str(self.roles["ROL04"].pk), keys)
        self.assertNotIn(str(self.roles["ROL01"].pk), keys)
        self.assertNotIn(str(self.roles["ROL02"].pk), keys)

    def test_users_opciones_rol_delegado_solo_rol04(self):
        self._login("delegado")
        resp = self.client.get(reverse("users"))
        keys = [o["value"] for o in resp.context["filters"][0]["options"]]
        self.assertEqual(keys, [str(self.roles["ROL04"].pk)])

    def test_users_opciones_delegacion_alcance(self):
        self._login("coordinador")
        resp = self.client.get(reverse("users"))
        keys = [o["value"] for o in resp.context["filters"][1]["options"]]
        self.assertIn(str(self.d1.pk), keys)
        self.assertIn(str(self.d2.pk), keys)

        self._login("delegado")
        resp = self.client.get(reverse("users"))
        keys = [o["value"] for o in resp.context["filters"][1]["options"]]
        self.assertEqual(keys, [str(self.d1.pk)])

    def test_users_filtrar_por_rol(self):
        self._login("superadmin")
        resp = self.client.get(
            reverse("users"), {"rol": str(self.roles["ROL04"].pk)},
        )
        self.assertEqual(resp.status_code, 200)
        roles = self._cell(resp, 3)
        self.assertTrue(all("ROL04" in t for t in roles))
        self.assertEqual(len(roles), 1)  # solo funcionario

    def test_users_filtrar_por_delegacion(self):
        self._login("superadmin")
        resp = self.client.get(
            reverse("users"), {"delegacion": str(self.d2.pk)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._row_texts(resp), [])

    def test_users_valor_invalido_se_ignora(self):
        self._login("superadmin")
        resp = self.client.get(reverse("users"), {"rol": "999999"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total"], 3)

    def test_attention_subtypes_filtro_tipo(self):
        from operaciones.models import AttentionSubtype
        from sgr_core.models import AttentionType

        tipo_a = AttentionType.objects.create(code="TATA", name="Tipo A")
        tipo_b = AttentionType.objects.create(code="TATB", name="Tipo B")
        AttentionSubtype.objects.create(
            code="SATA", name="Sub A", attention_type=tipo_a,
        )
        AttentionSubtype.objects.create(
            code="SATB", name="Sub B", attention_type=tipo_b,
        )

        self._login("superadmin")
        resp = self.client.get(
            reverse("attention_subtypes"), {"tipo": str(tipo_a.pk)},
        )
        self.assertEqual(resp.status_code, 200)
        codes = [row["cells"][0]["text"] for row in resp.context["rows"]]
        self.assertEqual(codes, ["SATA"])

    def test_attention_subtypes_valor_invalido_se_ignora(self):
        from operaciones.models import AttentionSubtype
        from sgr_core.models import AttentionType

        tipo_a = AttentionType.objects.create(code="TATA", name="Tipo A")
        AttentionSubtype.objects.create(
            code="SATA", name="Sub A", attention_type=tipo_a,
        )

        self._login("superadmin")
        resp = self.client.get(reverse("attention_subtypes"), {"tipo": "999999"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["rows"]), 1)

    def test_paginacion_conserva_filtro_rol(self):
        self._login("superadmin")
        for i in range(6):
            make_employee(
                f"emp{i}", f"9{i}.111.111-9", self.d1, self.roles["ROL04"],
            )
        resp = self.client.get(
            reverse("users"), {"rol": str(self.roles["ROL04"].pk), "page": 1},
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn(f"rol={self.roles['ROL04'].pk}", content)

    def test_paginacion_conserva_varios_filtros(self):
        self._login("superadmin")
        make_employee("emp6", "16.111.111-6", self.d1, self.roles["ROL04"])
        resp = self.client.get(
            reverse("users"),
            {
                "rol": str(self.roles["ROL04"].pk),
                "delegacion": str(self.d1.pk),
                "per_page": "10",
                "page": 1,
            },
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn(f"rol={self.roles['ROL04'].pk}", content)
        self.assertIn(f"delegacion={self.d1.pk}", content)
        self.assertIn("per_page=10", content)

    def test_export_url_conserva_filtros(self):
        self._login("superadmin")
        resp = self.client.get(
            reverse("users"), {"rol": str(self.roles["ROL04"].pk)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            f"rol={self.roles['ROL04'].pk}", resp.context["export_url"],
        )

    def test_etiquetas_filtro_activo(self):
        self._login("superadmin")
        resp = self.client.get(
            reverse("users"), {"rol": str(self.roles["ROL04"].pk)},
        )
        self.assertEqual(resp.status_code, 200)
        labels = [chip["text"] for chip in resp.context["active_filters"]
                  if chip["kind"] == "rol"]
        self.assertTrue(any("Rol:" in t for t in labels))
        urls = [chip["url"] for chip in resp.context["active_filters"]
                if chip["kind"] == "rol"]
        self.assertTrue(all("rol=" not in u for u in urls))
