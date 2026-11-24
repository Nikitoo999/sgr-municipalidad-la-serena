"""Organigrama de organizaciones comunitarias: niveles, vacantes y cargos."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from portal.tests.helpers import (
    DEMO_PASSWORD,
    TEST_STORAGES,
    ensure_roles,
    make_delegation,
    make_employee,
)
from sgr_core.models import CommunityOrganization, DirectiveRole, OrganizationMember


@override_settings(STORAGES=TEST_STORAGES)
class OrganigramaOrganizacionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02", color="#1D6FA5")
        cls.delegado = make_employee("delegado", "11.111.112-2", cls.d1, cls.roles["ROL03"])
        cls.funcionario = make_employee("funcionario", "11.111.113-3", cls.d1, cls.roles["ROL04"])
        cls.superadmin = User.objects.create_user(
            username="superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True,
        )
        cls.org = CommunityOrganization.objects.create(name="JJVV VILLA EL FARO", delegation=cls.d1, territory="T-04")
        cls.org2 = CommunityOrganization.objects.create(name="CLUB ADULTO MAYOR SOL", delegation=cls.d1)
        cls.org_ajena = CommunityOrganization.objects.create(name="CLUB DEL MAR", delegation=cls.d2)
        cls.presidente = DirectiveRole.objects.get(name="Presidente/a")
        cls.tesorero = DirectiveRole.objects.get(name="Tesorero/a")
        OrganizationMember.objects.create(
            organization=cls.org, role=cls.presidente, full_name="Patricia Soto",
            rut="13.442.810-4", phone="+56 9 8411 2290",
        )
        cls.url = reverse("organization_chart")

    def login(self, username):
        self.client.login(username=username, password=DEMO_PASSWORD)

    # ---- Vista ----
    def test_cargos_base_quedan_en_su_nivel(self):
        niveles = dict(DirectiveRole.objects.filter(is_base=True).values_list("name", "level"))
        self.assertEqual(niveles, {"Presidente/a": 1, "Secretario/a": 2, "Tesorero/a": 2})

    def test_dibuja_niveles_cubiertos_y_vacantes(self):
        self.login("delegado")
        resp = self.client.get(self.url, {"org": self.org.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Organigrama · JJVV VILLA EL FARO")
        self.assertContains(resp, "Nivel 1 · Presidencia")
        self.assertContains(resp, "Nivel 2 · Directiva")
        self.assertContains(resp, "Patricia Soto")
        self.assertContains(resp, "13.442.810-4")
        self.assertEqual(resp.context["cubiertos"], 1)
        self.assertEqual(resp.context["vacantes"], 2)
        self.assertContains(resp, 'data-state="vacant"', count=2)
        self.assertContains(resp, "Asignar a Tesorero/a")

    def test_lista_solo_organizaciones_del_alcance_y_busca(self):
        self.login("delegado")
        resp = self.client.get(self.url)
        nombres = [o.name for o in resp.context["organizaciones"]]
        self.assertEqual(nombres, ["CLUB ADULTO MAYOR SOL", "JJVV VILLA EL FARO"])
        resp = self.client.get(self.url, {"q": "faro"})
        self.assertEqual([o.name for o in resp.context["organizaciones"]], ["JJVV VILLA EL FARO"])
        # Una organización de otra delegación no se abre aunque se pida por URL.
        resp = self.client.get(self.url, {"org": self.org_ajena.pk})
        self.assertNotEqual(resp.context["org"], self.org_ajena)

    def test_funcionario_solo_consulta(self):
        self.login("funcionario")
        resp = self.client.get(self.url, {"org": self.org.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Patricia Soto")
        self.assertNotContains(resp, reverse("organization_member_save", args=[self.org.pk]))
        self.assertNotContains(resp, reverse("directive_role_create"))

    def test_ficha_enlaza_al_organigrama(self):
        self.login("delegado")
        resp = self.client.get(reverse("organizations_detail", args=[self.org.pk]))
        self.assertContains(resp, f"{self.url}?org={self.org.pk}")
        self.assertContains(resp, "Presidente/a:</strong> Patricia Soto")

    # ---- Integrantes ----
    def test_asignar_vacante_vuelve_al_organigrama(self):
        self.login("delegado")
        volver = f"{self.url}?org={self.org.pk}"
        resp = self.client.post(reverse("organization_member_save", args=[self.org.pk]), {
            "role": self.tesorero.pk, "full_name": "Mónica Contreras", "phone": "+56 9 6554 1198", "next": volver,
        })
        self.assertRedirects(resp, volver, fetch_redirect_response=False)
        self.assertTrue(OrganizationMember.alive.filter(organization=self.org, role=self.tesorero).exists())

    def test_next_externo_se_ignora(self):
        self.login("delegado")
        resp = self.client.post(reverse("organization_member_save", args=[self.org.pk]), {
            "role": self.tesorero.pk, "full_name": "Mónica Contreras", "next": "https://malicioso.example/",
        })
        self.assertRedirects(resp, f"{self.url}?org={self.org.pk}", fetch_redirect_response=False)

    def test_dejar_vacante(self):
        self.login("delegado")
        miembro = OrganizationMember.alive.get(organization=self.org, role=self.presidente)
        self.client.post(reverse("organization_member_remove", args=[self.org.pk, miembro.pk]))
        resp = self.client.get(self.url, {"org": self.org.pk})
        self.assertEqual(resp.context["cubiertos"], 0)
        self.assertEqual(resp.context["vacantes"], 3)

    # ---- Cargos directivos ----
    def test_crear_cargo_con_nivel_y_orden(self):
        self.login("delegado")
        self.client.post(reverse("directive_role_create"), {"name": "Vicepresidente/a", "level": "1", "order": "2"})
        role = DirectiveRole.objects.get(name="Vicepresidente/a")
        self.assertEqual((role.level, role.order, role.is_base), (1, 2, False))
        resp = self.client.get(self.url, {"org": self.org.pk})
        nivel1 = [n["role"].name for n in resp.context["niveles"][0]["nodes"]]
        self.assertEqual(nivel1, ["Presidente/a", "Vicepresidente/a"])

    def test_crear_cargo_repetido_o_nivel_invalido_se_rechaza(self):
        self.login("delegado")
        self.client.post(reverse("directive_role_create"), {"name": "presidente/a", "level": "1"})
        self.client.post(reverse("directive_role_create"), {"name": "Vocal", "level": "9"})
        self.assertEqual(DirectiveRole.objects.filter(name__iexact="presidente/a").count(), 1)
        self.assertFalse(DirectiveRole.objects.filter(name="Vocal").exists())

    def test_editar_cargo_creado_y_base_no_se_renombra(self):
        vocal = DirectiveRole.objects.create(name="Vocal", level=3, order=10)
        self.login("delegado")
        self.client.post(reverse("directive_role_update", args=[vocal.pk]),
                         {"name": "Vocal primero/a", "level": "2", "order": "5"})
        vocal.refresh_from_db()
        self.assertEqual((vocal.name, vocal.level, vocal.order), ("Vocal primero/a", 2, 5))
        self.client.post(reverse("directive_role_update", args=[self.presidente.pk]),
                         {"name": "Jefe", "level": "1", "order": "1"})
        self.presidente.refresh_from_db()
        self.assertEqual(self.presidente.name, "Presidente/a")

    def test_solo_superadmin_elimina_cargos(self):
        vocal = DirectiveRole.objects.create(name="Vocal", level=3)
        self.login("delegado")
        resp = self.client.post(reverse("directive_role_delete", args=[vocal.pk]))
        self.assertEqual(resp.status_code, 403)
        self.client.logout()
        self.login("superadmin")
        self.client.post(reverse("directive_role_delete", args=[vocal.pk]))
        vocal.refresh_from_db()
        self.assertIsNotNone(vocal.deleted_at)

    def test_no_se_elimina_cargo_base_ni_cargo_ocupado(self):
        vocal = DirectiveRole.objects.create(name="Vocal", level=3)
        OrganizationMember.objects.create(organization=self.org, role=vocal, full_name="Rodrigo Vera")
        self.login("superadmin")
        self.client.post(reverse("directive_role_delete", args=[vocal.pk]))
        self.client.post(reverse("directive_role_delete", args=[self.presidente.pk]))
        vocal.refresh_from_db()
        self.presidente.refresh_from_db()
        self.assertIsNone(vocal.deleted_at)
        self.assertIsNone(self.presidente.deleted_at)

    def test_funcionario_no_gestiona_cargos(self):
        self.login("funcionario")
        resp = self.client.post(reverse("directive_role_update", args=[self.tesorero.pk]), {"level": "3"})
        self.assertEqual(resp.status_code, 403)

    def test_filtro_respeta_hidden(self):
        css = (Path(settings.BASE_DIR) / "portal/static/portal/css/org_chart.css").read_text(encoding="utf-8")
        self.assertIn(".oc-level[hidden],.oc-node[hidden]", css)
