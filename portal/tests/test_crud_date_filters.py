"""Pruebas de los filtros de fecha y los filtros propios del motor CRUD."""

from datetime import datetime, time, timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from openpyxl import load_workbook

from portal.tests.utils import TEST_STORAGES
from sgr_core.models import (
    AttentionSubtype,
    AttentionType,
    Delegation,
    ProjectItem,
    Role,
    RolePermission,
)
from sgr_core.roles import ensure_base_roles


@override_settings(STORAGES=TEST_STORAGES)
class CrudDateFiltersTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_base_roles(Role, RolePermission)
        cls.user = User.objects.create_user(
            username="superadmin",
            password="test-password",
            is_superuser=True,
            is_staff=True,
        )
        cls.today = timezone.localdate()
        cls.in_range = [
            cls._create_delegation(f"Rango {index}", f"DEL{index:02d}", cls.today)
            for index in range(1, 9)
        ]
        cls.before = cls._create_delegation(
            "Fecha anterior", "DEL09", cls.today - timedelta(days=1),
        )
        cls.after = cls._create_delegation(
            "Fecha posterior", "DEL10", cls.today + timedelta(days=1),
        )

        cls.item_with_description = ProjectItem.objects.create(
            code="ITM091", name="Ítem descrito", description="Tiene detalle",
        )
        cls.item_without_description = ProjectItem.objects.create(
            code="ITM092", name="Ítem sin detalle", description="",
        )

        cls.type_with_subtypes = AttentionType.objects.create(
            code="TAT91", name="Tipo con sub atención",
        )
        cls.type_without_subtypes = AttentionType.objects.create(
            code="TAT92", name="Tipo sin sub atención",
        )
        cls.type_with_deleted_subtype = AttentionType.objects.create(
            code="TAT93", name="Tipo con sub atención borrada",
        )
        AttentionSubtype.objects.create(
            code="SAT091", name="Sub atención vigente",
            attention_type=cls.type_with_subtypes,
        )
        deleted_subtype = AttentionSubtype.objects.create(
            code="SAT092", name="Sub atención borrada",
            attention_type=cls.type_with_deleted_subtype,
        )
        AttentionSubtype.objects.filter(pk=deleted_subtype.pk).update(
            deleted_at=timezone.now(),
        )

    @staticmethod
    def _create_delegation(name, code, created_on):
        delegation = Delegation.objects.create(
            name=name,
            code=code,
            commune="La Serena",
            address="",
            color="#C62828",
        )
        created_at = timezone.make_aware(
            datetime.combine(created_on, time(hour=12)),
        )
        Delegation.objects.filter(pk=delegation.pk).update(created_at=created_at)
        return delegation

    def setUp(self):
        self.client.login(username="superadmin", password="test-password")

    def _date_range(self, **params):
        return self.client.get(reverse("delegations"), params)

    def test_rango_valido_filtra_desde_y_hasta_inclusive(self):
        response = self._date_range(
            desde=self.today.isoformat(),
            hasta=self.today.isoformat(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], len(self.in_range))
        shown = {row["cells"][1]["text"] for row in response.context["rows"]}
        self.assertTrue(shown.issubset({item.name for item in self.in_range}))

    def test_solo_desde_filtra(self):
        response = self._date_range(desde=self.today.isoformat())

        self.assertEqual(response.context["total"], len(self.in_range) + 1)

    def test_solo_hasta_filtra(self):
        response = self._date_range(hasta=self.today.isoformat())

        self.assertEqual(response.context["total"], len(self.in_range) + 1)

    def test_desde_posterior_a_hasta_ignora_rango_y_muestra_aviso(self):
        response = self._date_range(
            desde=(self.today + timedelta(days=1)).isoformat(),
            hasta=self.today.isoformat(),
        )

        self.assertEqual(response.context["total"], len(self.in_range) + 2)
        self.assertEqual(response.context["date_from"], "")
        self.assertEqual(response.context["date_to"], "")
        self.assertEqual(
            response.context["date_error"],
            "La fecha «Desde» no puede ser posterior a «Hasta»: se ignoró el rango.",
        )
        self.assertContains(response, '<p class="filter-warning" role="alert">')

    def test_fecha_invalida_se_ignora(self):
        response = self._date_range(desde="no-es-fecha")

        self.assertEqual(response.context["total"], len(self.in_range) + 2)
        self.assertEqual(response.context["date_from"], "")
        self.assertEqual(response.context["date_error"], "")

    def test_paginacion_conserva_el_rango(self):
        response = self._date_range(
            desde=self.today.isoformat(),
            hasta=self.today.isoformat(),
        )
        page_two = next(
            link for link in response.context["page_links"]
            if link["number"] == 2
        )

        self.assertIn(f"desde={self.today.isoformat()}", page_two["url"])
        self.assertIn(f"hasta={self.today.isoformat()}", page_two["url"])
        next_page = self.client.get(reverse("delegations") + page_two["url"])
        self.assertEqual(next_page.context["total"], len(self.in_range))

    def test_exportacion_excel_respeta_el_rango(self):
        response = self.client.get(
            reverse("delegations_export"),
            {
                "desde": self.today.isoformat(),
                "hasta": self.today.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        exported_codes = [
            row[0]
            for row in workbook.active.iter_rows(min_row=2, max_col=1, values_only=True)
        ]
        self.assertCountEqual(exported_codes, [item.code for item in self.in_range])

    def test_filtro_de_items_con_o_sin_descripcion(self):
        with_description = self.client.get(
            reverse("items"), {"descripcion": "con"},
        )
        without_description = self.client.get(
            reverse("items"), {"descripcion": "sin"},
        )

        self.assertEqual(with_description.context["total"], 1)
        self.assertEqual(without_description.context["total"], 1)
        self.assertEqual(
            with_description.context["rows"][0]["cells"][1]["text"],
            self.item_with_description.name,
        )
        self.assertEqual(
            without_description.context["rows"][0]["cells"][1]["text"],
            self.item_without_description.name,
        )

    def test_filtro_de_tipos_considera_solo_sub_atenciones_vigentes(self):
        with_subtypes = self.client.get(
            reverse("attention_types"), {"subatenciones": "con"},
        )
        without_subtypes = self.client.get(
            reverse("attention_types"), {"subatenciones": "sin"},
        )

        self.assertEqual(with_subtypes.context["total"], 1)
        self.assertEqual(without_subtypes.context["total"], 2)
        self.assertEqual(
            with_subtypes.context["rows"][0]["cells"][1]["text"],
            self.type_with_subtypes.name,
        )
        without_names = {
            row["cells"][1]["text"] for row in without_subtypes.context["rows"]
        }
        self.assertEqual(
            without_names,
            {
                self.type_without_subtypes.name,
                self.type_with_deleted_subtype.name,
            },
        )
